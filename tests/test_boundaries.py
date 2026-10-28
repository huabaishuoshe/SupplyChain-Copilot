import math

import pandas as pd
import pytest

from supplychain_copilot.calculations import analyze_inventory
from supplychain_copilot.validation import NUMERIC_COLUMNS, REQUIRED_COLUMNS, validate_inventory


def inventory(**overrides):
    row = dict(sku="001", product_name="测试商品", current_stock=20,
               avg_daily_demand=10, lead_time_days=5, safety_stock_days=2)
    row.update(overrides)
    return pd.DataFrame([row])


def test_lead_time_and_replenishment():
    out = analyze_inventory(inventory()).iloc[0]
    assert out.coverage_days == 2
    assert out.lead_time_demand == 50
    assert out.safety_stock == 20
    assert out.target_stock == 70
    assert out.recommended_reorder_qty == 50
    assert out.stockout_risk == "高"


@pytest.mark.parametrize("stock,risk", [(0, "高"), (49, "高"), (50, "中"), (69, "中"), (70, "低")])
def test_risk_boundaries(stock, risk):
    assert analyze_inventory(inventory(current_stock=stock)).iloc[0].stockout_risk == risk


@pytest.mark.parametrize("transit,reorder,overstock", [(0, 50, 0), (30, 20, 0), (50, 0, 0), (100, 0, 50)])
def test_in_transit_inventory(transit, reorder, overstock):
    row = analyze_inventory(inventory(in_transit_stock=transit)).iloc[0]
    assert row.inventory_position == 20 + transit
    assert row.recommended_reorder_qty == reorder
    assert row.potential_overstock == overstock
    assert row.stockout_risk == "高"  # Arrival timing is not provided.


def test_missing_transit_is_explicit_zero_with_warning():
    result = validate_inventory(inventory())
    assert result.valid
    assert result.cleaned.iloc[0].in_transit_stock == 0
    assert any("in_transit_stock" in warning for warning in result.warnings)


@pytest.mark.parametrize("column", NUMERIC_COLUMNS + ["in_transit_stock"])
@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), -1, "bad", True, 1 + 2j])
def test_invalid_numeric_values(column, value):
    df = inventory(**{column: value})
    assert not validate_inventory(df).valid
    with pytest.raises(ValueError):
        analyze_inventory(df)


def test_missing_lead_time_column():
    assert not validate_inventory(inventory().drop(columns="lead_time_days")).valid


def test_empty_data():
    assert not validate_inventory(pd.DataFrame(columns=REQUIRED_COLUMNS)).valid


@pytest.mark.parametrize("column", ["sku", "product_name"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_labels(column, value):
    assert not validate_inventory(inventory(**{column: value})).valid


def test_whitespace_duplicate_sku():
    df = pd.concat([inventory(sku=" A "), inventory(sku="A")], ignore_index=True)
    assert not validate_inventory(df).valid


def test_duplicate_columns():
    df = inventory()
    df = pd.concat([df, df[["sku"]]], axis=1)
    assert not validate_inventory(df).valid


def test_round_up_fractional_reorder():
    assert analyze_inventory(inventory(current_stock=20.2)).iloc[0].recommended_reorder_qty == 50


def test_zero_demand_with_transit():
    row = analyze_inventory(inventory(avg_daily_demand=0, in_transit_stock=10)).iloc[0]
    assert math.isnan(row.coverage_days)
    assert row.lead_time_demand == 0
    assert row.recommended_reorder_qty == 0
    assert row.potential_overstock == 30
    assert row.stockout_risk == "无需求"


def test_overflow_is_reported():
    with pytest.raises(ValueError, match="有限数值范围"):
        analyze_inventory(inventory(avg_daily_demand=1e308, lead_time_days=1e308))


def test_input_frame_not_mutated():
    df = inventory()
    original = df.copy(deep=True)
    analyze_inventory(df)
    pd.testing.assert_frame_equal(df, original)
