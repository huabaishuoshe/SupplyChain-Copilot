import pandas as pd
import pytest
from supplychain_copilot.calculations import analyze_inventory
from supplychain_copilot.validation import validate_inventory

def frame(**overrides):
    row = {"sku":"A", "product_name":"A product", "current_stock":100, "avg_daily_demand":10, "lead_time_days":5, "safety_stock_days":2}
    row.update(overrides); return pd.DataFrame([row])

def test_normal_metrics():
    out = analyze_inventory(frame()); assert out.loc[0,"coverage_days"] == 10; assert out.loc[0,"recommended_reorder_qty"] == 0; assert out.loc[0,"potential_overstock"] == 30; assert out.loc[0,"stockout_risk"] == "低"
def test_missing_column():
    result = validate_inventory(frame().drop(columns=["sku"])); assert not result.valid; assert "sku" in result.errors[0]
def test_zero_demand():
    out = analyze_inventory(frame(avg_daily_demand=0)); assert pd.isna(out.loc[0,"coverage_days"]); assert out.loc[0,"recommended_reorder_qty"] == 0; assert out.loc[0,"stockout_risk"] == "无需求"
@pytest.mark.parametrize("column", ["current_stock","avg_daily_demand","lead_time_days","safety_stock_days"])
def test_negative_input(column):
    result = validate_inventory(frame(**{column:-1})); assert not result.valid; assert any("不能为负数" in e for e in result.errors)
def test_non_numeric_input():
    result = validate_inventory(frame(current_stock="bad")); assert not result.valid; assert any("必须是数值" in e for e in result.errors)
def test_duplicate_sku():
    result = validate_inventory(pd.concat([frame(), frame()])); assert not result.valid; assert any("唯一" in e for e in result.errors)
