import pandas as pd
import pytest

from supplychain_copilot.calculations import analyze_inventory
from supplychain_copilot.scenarios import ScenarioParameters, adjust_inventory, compare_scenarios
from supplychain_copilot.suppliers import summarize_suppliers


def inventory(**overrides):
    row = dict(sku="A", product_name="虚构测试", current_stock=70, avg_daily_demand=10,
               lead_time_days=5, safety_stock_days=2, in_transit_stock=0)
    row.update(overrides)
    return pd.DataFrame([row])


def test_demand_increase_changes_risk():
    c = compare_scenarios(inventory(), ScenarioParameters(demand_change_pct=100))
    assert c.baseline.iloc[0].stockout_risk == "低"
    assert c.adjusted.iloc[0].stockout_risk == "高"
    assert c.adjusted.iloc[0].coverage_days == 3.5
    assert c.adjusted.iloc[0].lead_time_demand == 100
    assert c.summary.loc["高风险 SKU 数", "调整后"] == 1


def test_longer_lead_time_changes_risk():
    c = compare_scenarios(inventory(), ScenarioParameters(lead_time_change_days=3))
    assert c.adjusted.iloc[0].lead_time_days == 8
    assert c.adjusted.iloc[0].stockout_risk == "高"


def test_stock_reduction_increases_reorder():
    c = compare_scenarios(inventory(), ScenarioParameters(stock_change_pct=-50))
    assert c.baseline.iloc[0].recommended_reorder_qty == 0
    assert c.adjusted.iloc[0].recommended_reorder_qty == 35


def test_signed_lead_end_projection_excludes_transit_and_new_orders():
    c = compare_scenarios(inventory(current_stock=20, in_transit_stock=1000), ScenarioParameters())
    assert c.adjusted.iloc[0].projected_available_at_lead_end == -30
    assert c.adjusted.iloc[0].recommended_reorder_qty == 0
    assert c.adjusted.iloc[0].stockout_risk == "高"


def test_scenario_cannot_mutate_source():
    df = inventory(supplier="测试供应商")
    original = df.copy(deep=True)
    compare_scenarios(df, ScenarioParameters(10, 2, -20, 5))
    pd.testing.assert_frame_equal(df, original)


def test_reset_defaults_preserve_per_sku_safety_days():
    df = pd.concat([inventory(), inventory(sku="B", safety_stock_days=8)], ignore_index=True)
    c = compare_scenarios(df, ScenarioParameters())
    pd.testing.assert_frame_equal(c.baseline, c.adjusted)
    assert c.adjusted.safety_stock_days.tolist() == [2, 8]


def test_safety_stock_override():
    c = compare_scenarios(inventory(), ScenarioParameters(safety_stock_days=5))
    assert c.adjusted.iloc[0].target_stock == 100
    assert c.adjusted.iloc[0].stockout_risk == "中"
    assert c.summary.loc["中风险 SKU 数", "调整后"] == 1


@pytest.mark.parametrize("kwargs", [dict(demand_change_pct=-101), dict(stock_change_pct=-101),
    dict(lead_time_change_days=-6), dict(lead_time_change_days=float("inf")),
    dict(demand_change_pct=float("nan")), dict(safety_stock_days=-1), dict(stock_change_pct=True)])
def test_invalid_scenario_rejected(kwargs):
    with pytest.raises(ValueError):
        compare_scenarios(inventory(), ScenarioParameters(**kwargs))


def test_zero_demand_scenario():
    c = compare_scenarios(inventory(), ScenarioParameters(demand_change_pct=-100))
    assert c.adjusted.iloc[0].stockout_risk == "无需求"
    assert pd.isna(c.adjusted.iloc[0].coverage_days)
    assert c.adjusted.iloc[0].recommended_reorder_qty == 0
    assert c.summary.loc["潜在积压 SKU 数", "调整后"] == 1


def test_supplier_aggregation_and_risk_counts():
    df = pd.concat([inventory(supplier="甲"), inventory(sku="B", supplier="甲", current_stock=10),
                    inventory(sku="C", supplier="乙", current_stock=60)], ignore_index=True)
    out = summarize_suppliers(analyze_inventory(df)).set_index("supplier")
    assert out.loc["甲", "sku_count"] == 2
    assert out.loc["甲", "high_risk_skus"] == out.loc["甲", "low_risk_skus"] == 1
    assert out.loc["甲", "current_stock"] == 80
    assert out.loc["甲", "recommended_reorder_qty"] == 60
    assert out.loc["乙", "medium_risk_skus"] == 1
    assert "on_time_delivery_rate" not in out


def test_missing_supplier_does_not_break_inventory():
    out = analyze_inventory(inventory())
    assert out.iloc[0].recommended_reorder_qty == 0
    assert summarize_suppliers(out).empty


def test_blank_suppliers_not_dropped_and_source_not_mutated():
    df = pd.concat([inventory(supplier=" "), inventory(sku="B", supplier=None)], ignore_index=True)
    result = analyze_inventory(df)
    original = result.copy(deep=True)
    summary = summarize_suppliers(result)
    assert summary.iloc[0].supplier == "未填写供应商"
    assert summary.iloc[0].sku_count == 2
    assert summary.iloc[0].current_stock == 140
    pd.testing.assert_frame_equal(result, original)
