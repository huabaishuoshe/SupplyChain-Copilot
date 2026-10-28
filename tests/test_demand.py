import math
from statistics import NormalDist

import pandas as pd
import pytest

from supplychain_copilot.demand import calculate_demand_statistics, validate_demand_history
from supplychain_copilot.calculations import analyze_inventory
from supplychain_copilot.strategies import compare_inventory_policies


def history(values=(2, 4, 6), sku="A"):
    # Deliberately fictional test observations; never loaded into the app by default.
    return pd.DataFrame(dict(date=pd.date_range("2026-01-01", periods=len(values)).strftime("%Y-%m-%d"),
                             sku=sku, demand=values))


def stock(**overrides):
    row = dict(sku="A", product_name="虚构测试", current_stock=10, avg_daily_demand=9,
               lead_time_days=4, safety_stock_days=2, in_transit_stock=0)
    row.update(overrides)
    return pd.DataFrame([row])


def test_sample_std_and_cv():
    stats = calculate_demand_statistics(history(), 3).iloc[0]
    assert stats.history_usable
    assert stats.history_mean_daily_demand == 4
    assert stats.daily_demand_std == 2  # ddof=1, not population standard deviation.
    assert stats.demand_cv == 0.5
    assert stats.n_observations == stats.span_days == 3


@pytest.mark.parametrize("column,value", [("date", "bad"), ("date", "2026-02-30"),
    ("date", "2026-01-01T12:00:00"), ("sku", " "), ("demand", None),
    ("demand", -1), ("demand", float("inf")), ("demand", "bad"), ("demand", True)])
def test_invalid_history(column, value):
    df = history().astype(object)
    df.loc[0, column] = value
    assert not validate_demand_history(df).valid
    with pytest.raises(ValueError):
        calculate_demand_statistics(df, 3)


def test_duplicate_sku_date_rejected():
    df = pd.concat([history(), history().iloc[:1]])
    assert not validate_demand_history(df).valid


def test_missing_schema_and_empty_history():
    assert not validate_demand_history(history().drop(columns="date")).valid
    assert not validate_demand_history(history().iloc[:0]).valid


def test_insufficient_observations_have_no_misleading_statistics():
    row = calculate_demand_statistics(history()).iloc[0]
    assert row.history_status == "观测不足"
    assert not row.history_usable
    assert pd.isna(row.history_mean_daily_demand)
    assert pd.isna(row.daily_demand_std) and pd.isna(row.demand_cv)


def test_calendar_gaps_not_imputed_to_zero():
    row = calculate_demand_statistics(history().iloc[[0, 2]], 2).iloc[0]
    assert row.missing_days == 1
    assert row.history_status == "存在缺失日期"
    assert pd.isna(row.daily_demand_std)


def test_zero_mean_not_used_for_variability():
    row = calculate_demand_statistics(history((0, 0, 0)), 3).iloc[0]
    assert row.history_mean_daily_demand == 0
    assert not row.history_usable
    assert pd.isna(row.demand_cv) and pd.isna(row.daily_demand_std)


def test_constant_positive_demand_has_real_zero_std():
    row = calculate_demand_statistics(history((4, 4, 4)), 3).iloc[0]
    assert row.history_usable
    assert row.daily_demand_std == 0 and row.demand_cv == 0


def test_unsorted_history_and_no_mutation():
    df = history().iloc[::-1]
    original = df.copy(deep=True)
    assert calculate_demand_statistics(df, 3).iloc[0].daily_demand_std == 2
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("minimum", [1, 0, 2.5, True])
def test_invalid_minimum(minimum):
    with pytest.raises(ValueError):
        calculate_demand_statistics(history(), minimum)


def test_variability_safety_stock_formula():
    stats = calculate_demand_statistics(history(), 3)
    result = analyze_inventory(stock(), safety_stock_strategy="variability", demand_statistics=stats).iloc[0]
    expected = NormalDist().inv_cdf(0.95) * 2 * math.sqrt(4)
    assert result.avg_daily_demand == 4
    assert result.safety_stock == pytest.approx(expected)
    assert result.target_stock == pytest.approx(16 + expected)
    assert result.recommended_reorder_qty == math.ceil(16 + expected - 10)
    assert result.safety_stock_policy == "需求波动"


def test_no_history_keeps_fixed_policy():
    expected = analyze_inventory(stock())
    actual = analyze_inventory(stock(), safety_stock_strategy="variability")
    assert actual.iloc[0].safety_stock_policy == "固定天数"
    assert actual.iloc[0].recommended_reorder_qty == expected.iloc[0].recommended_reorder_qty
    assert actual.iloc[0].avg_daily_demand == 9


def test_partial_history_falls_back_per_sku():
    df = pd.concat([stock(), stock(sku="B")], ignore_index=True)
    stats = calculate_demand_statistics(history(), 3)
    out = analyze_inventory(df, safety_stock_strategy="variability", demand_statistics=stats)
    assert out.safety_stock_policy.tolist() == ["需求波动", "固定天数"]
    assert out.avg_daily_demand.tolist() == [4, 9]


def test_insufficient_history_fallback():
    stats = calculate_demand_statistics(history())
    out = analyze_inventory(stock(), safety_stock_strategy="variability", demand_statistics=stats).iloc[0]
    assert out.safety_stock_policy == "固定天数"
    assert "至少需要" in out.policy_note


def test_policy_comparison_uses_equal_mean_and_does_not_modify_inputs():
    df = stock()
    stats = calculate_demand_statistics(history(), 3)
    original, original_stats = df.copy(deep=True), stats.copy(deep=True)
    fixed, variable = compare_inventory_policies(df, stats)
    assert fixed.iloc[0].avg_daily_demand == variable.iloc[0].avg_daily_demand == 4
    assert fixed.iloc[0].safety_stock == 8
    pd.testing.assert_frame_equal(df, original)
    pd.testing.assert_frame_equal(stats, original_stats)


def test_higher_service_level_increases_safety_stock():
    stats = calculate_demand_statistics(history(), 3)
    low = analyze_inventory(stock(), safety_stock_strategy="variability", demand_statistics=stats, service_level=.9)
    high = analyze_inventory(stock(), safety_stock_strategy="variability", demand_statistics=stats, service_level=.99)
    assert high.iloc[0].safety_stock > low.iloc[0].safety_stock


@pytest.mark.parametrize("level", [.5, 1, float("nan"), True])
def test_invalid_service_level(level):
    with pytest.raises(ValueError):
        analyze_inventory(stock(), service_level=level)
