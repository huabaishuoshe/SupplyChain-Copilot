"""Deterministic what-if comparisons; source inventory is never mutated."""

from dataclasses import dataclass
import math
from numbers import Real

import pandas as pd

from .calculations import analyze_inventory
from .validation import validate_inventory


@dataclass(frozen=True)
class ScenarioParameters:
    demand_change_pct: float = 0.0
    lead_time_change_days: float = 0.0
    stock_change_pct: float = 0.0
    safety_stock_days: float | None = None


@dataclass
class ScenarioComparison:
    baseline: pd.DataFrame
    adjusted: pd.DataFrame
    summary: pd.DataFrame
    detail: pd.DataFrame


def adjust_inventory(inventory: pd.DataFrame, parameters: ScenarioParameters) -> pd.DataFrame:
    if not isinstance(parameters, ScenarioParameters):
        raise ValueError("情景参数类型无效。")
    for value in [parameters.demand_change_pct, parameters.lead_time_change_days,
                  parameters.stock_change_pct, parameters.safety_stock_days]:
        if value is not None and (isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value)):
            raise ValueError("情景参数必须是有限数值。")
    if parameters.demand_change_pct < -100 or parameters.stock_change_pct < -100:
        raise ValueError("需求与库存变化比例不能小于 -100%。")
    if parameters.safety_stock_days is not None and parameters.safety_stock_days < 0:
        raise ValueError("安全库存天数不能为负数。")
    validated = validate_inventory(inventory)
    if not validated.valid:
        raise ValueError("; ".join(validated.errors))
    adjusted = validated.cleaned.copy(deep=True)
    adjusted["avg_daily_demand"] = adjusted.avg_daily_demand.astype(float) * (1 + parameters.demand_change_pct / 100)
    adjusted["current_stock"] = adjusted.current_stock.astype(float) * (1 + parameters.stock_change_pct / 100)
    adjusted["lead_time_days"] = adjusted.lead_time_days.astype(float) + parameters.lead_time_change_days
    if (adjusted.lead_time_days < 0).any():
        raise ValueError("调整后存在负交期，请减小交期缩短幅度。")
    if parameters.safety_stock_days is not None:
        adjusted["safety_stock_days"] = float(parameters.safety_stock_days)
    return adjusted


def summarize_inventory(result: pd.DataFrame) -> pd.Series:
    return pd.Series({
        "高风险 SKU 数": int(result.stockout_risk.eq("高").sum()),
        "中风险 SKU 数": int(result.stockout_risk.eq("中").sum()),
        "潜在积压 SKU 数": int(result.potential_overstock.gt(0).sum()),
        "建议补货总量": sum(result.recommended_reorder_qty.tolist()),
    })


def compare_scenarios(inventory: pd.DataFrame, parameters: ScenarioParameters) -> ScenarioComparison:
    baseline = analyze_inventory(inventory)
    adjusted = analyze_inventory(adjust_inventory(inventory, parameters))
    summary = pd.DataFrame({"基准": summarize_inventory(baseline), "调整后": summarize_inventory(adjusted)})
    summary["变化"] = summary["调整后"] - summary["基准"]
    fields = ["coverage_days", "lead_time_days", "lead_time_demand", "projected_available_at_lead_end",
              "current_stock", "safety_stock_days", "safety_stock", "target_stock",
              "recommended_reorder_qty", "potential_overstock", "stockout_risk"]
    detail = baseline[["sku", "product_name"]].copy()
    for field in fields:
        detail[f"{field}_baseline"] = baseline[field].to_numpy()
        detail[f"{field}_scenario"] = adjusted[field].to_numpy()
    return ScenarioComparison(baseline, adjusted, summary, detail)
