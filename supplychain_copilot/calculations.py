import math
import pandas as pd
from .validation import validate_inventory
from .strategies import apply_safety_stock_policy

def analyze_inventory(df: pd.DataFrame, *, safety_stock_strategy="fixed", demand_statistics=None,
                      service_level=0.95) -> pd.DataFrame:
    validation = validate_inventory(df)
    if not validation.valid:
        raise ValueError("; ".join(validation.errors))
    result = validation.cleaned.copy()
    # Use floating point for intermediate arithmetic to avoid integer overflow.
    numeric = ["current_stock", "avg_daily_demand", "lead_time_days", "safety_stock_days", "in_transit_stock"]
    result[numeric] = result[numeric].astype(float)
    result = apply_safety_stock_policy(result, safety_stock_strategy, demand_statistics, service_level)
    demand = result["avg_daily_demand"]
    result["coverage_days"] = result["current_stock"].div(demand.where(demand > 0))
    result["lead_time_demand"] = demand * result["lead_time_days"]
    result["safety_stock"] = demand * result["safety_stock_days"]
    variable = result["safety_stock_policy"].eq("需求波动")
    result.loc[variable, "safety_stock"] = result.loc[variable, "statistical_safety_stock"]
    target_days = result["lead_time_days"] + result["safety_stock_days"]
    result["target_stock"] = demand * target_days
    result.loc[variable, "target_stock"] = (result.loc[variable, "lead_time_demand"]
                                            + result.loc[variable, "safety_stock"])
    result["projected_available_at_lead_end"] = result["current_stock"] - result["lead_time_demand"]
    result["inventory_position"] = result["current_stock"] + result["in_transit_stock"]
    result["potential_overstock"] = (result["inventory_position"] - result["target_stock"]).clip(lower=0)
    computed = ["lead_time_demand", "safety_stock", "target_stock", "inventory_position", "potential_overstock", "projected_available_at_lead_end"]
    if not result[computed].apply(lambda col: col.map(math.isfinite)).all().all() or not result.loc[demand > 0, "coverage_days"].map(math.isfinite).all():
        raise ValueError("计算结果超出有限数值范围，请检查输入的数量和天数。")
    result["recommended_reorder_qty"] = (result["target_stock"] - result["inventory_position"]).clip(lower=0).apply(math.ceil)
    def risk(row):
        # Risk deliberately uses on-hand stock: transit arrival dates are unknown.
        if row["avg_daily_demand"] == 0: return "无需求"
        if row["coverage_days"] < row["lead_time_days"]: return "高"
        if row["current_stock"] < row["target_stock"]: return "中"
        return "低"
    result["stockout_risk"] = result.apply(risk, axis=1)
    return result
