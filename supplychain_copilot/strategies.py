"""Safety-stock policies. No forecasts or synthetic history are generated."""

import math
from statistics import NormalDist

import pandas as pd


def apply_safety_stock_policy(result, strategy="fixed", demand_statistics=None, service_level=0.95):
    if strategy not in {"fixed", "variability"}:
        raise ValueError("未知安全库存策略。")
    if isinstance(service_level, bool) or not isinstance(service_level, (int, float)) or not math.isfinite(service_level) or not 0.5 < service_level < 1:
        raise ValueError("周期服务水平必须满足 0.5 < alpha < 1。")
    result = result.copy(deep=True)
    result["demand_source"] = "库存输入日均需求"
    result["safety_stock_policy"] = "固定天数"
    result["policy_note"] = "使用输入的固定安全库存天数。"
    result["statistical_safety_stock"] = float("nan")
    if strategy == "fixed":
        return result
    result["policy_note"] = "无匹配的可用历史需求，回退固定天数策略。"
    if demand_statistics is None:
        return result
    required = {"sku", "history_usable", "history_mean_daily_demand", "daily_demand_std", "history_message"}
    if not isinstance(demand_statistics, pd.DataFrame) or not required.issubset(demand_statistics.columns):
        raise ValueError("需求统计表结构无效，请先计算历史需求统计。")
    if demand_statistics.sku.duplicated().any():
        raise ValueError("需求统计表中的 SKU 必须唯一。")
    matched = demand_statistics.set_index("sku").reindex(result.sku.tolist())
    matched.index = result.index
    usable = matched.history_usable.eq(True).fillna(False)
    result["policy_note"] = matched.history_message.fillna(result["policy_note"]).astype(str)
    for column, strictly_positive in [("history_mean_daily_demand", True), ("daily_demand_std", False)]:
        numbers = pd.to_numeric(matched.loc[usable, column], errors="coerce")
        if numbers.isna().any() or not numbers.map(math.isfinite).all() or ((numbers <= 0) if strictly_positive else (numbers < 0)).any():
            raise ValueError("可用需求统计中的均值或标准差无效。")
    result.loc[usable, "avg_daily_demand"] = matched.loc[usable, "history_mean_daily_demand"].to_numpy()
    z = NormalDist().inv_cdf(service_level)
    result.loc[usable, "statistical_safety_stock"] = (
        z * matched.loc[usable, "daily_demand_std"].to_numpy()
        * result.loc[usable, "lead_time_days"].map(math.sqrt).to_numpy())
    result.loc[usable, "demand_source"] = "可用历史日均需求"
    result.loc[usable, "safety_stock_policy"] = "需求波动"
    result.loc[usable, "policy_note"] = f"z×日需求样本标准差×sqrt(交期)；周期服务水平假设 {service_level:.2%}。"
    return result


def compare_inventory_policies(inventory, demand_statistics=None, service_level=0.95):
    # Local import avoids a module cycle: the calculation engine uses the helper above.
    from .calculations import analyze_inventory

    variable = analyze_inventory(inventory, safety_stock_strategy="variability",
                                 demand_statistics=demand_statistics, service_level=service_level)
    aligned = inventory.copy(deep=True)
    # Both candidates use the same D; only their safety-stock method differs.
    aligned["avg_daily_demand"] = variable.avg_daily_demand.to_numpy()
    fixed = analyze_inventory(aligned)
    fixed["demand_source"] = variable.demand_source.to_numpy()
    return fixed, variable
