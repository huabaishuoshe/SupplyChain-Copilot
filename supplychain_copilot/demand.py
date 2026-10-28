"""Validate real daily observations and estimate descriptive demand variation."""

import math
from statistics import mean, stdev

import pandas as pd

from .validation import ValidationResult

HISTORY_COLUMNS = ["date", "sku", "demand"]
STAT_COLUMNS = ["sku", "n_observations", "span_days", "missing_days", "start_date", "end_date",
                "history_mean_daily_demand", "daily_demand_std", "demand_cv",
                "history_usable", "history_status", "history_message"]


def validate_demand_history(df: pd.DataFrame) -> ValidationResult:
    if not isinstance(df, pd.DataFrame):
        return ValidationResult(False, ["历史数据必须是 DataFrame。"])
    if df.columns.duplicated().any():
        return ValidationResult(False, ["历史数据列名不能重复。"])
    missing = [c for c in HISTORY_COLUMNS if c not in df]
    if missing:
        return ValidationResult(False, [f"历史数据缺少必需列: {', '.join(missing)}"])
    cleaned = df[HISTORY_COLUMNS].copy()
    errors = []
    if cleaned.empty:
        errors.append("历史数据不能为空。")
    cleaned["sku"] = cleaned["sku"].astype("string").str.strip()
    if cleaned.sku.isna().any() or cleaned.sku.eq("").any():
        errors.append("历史数据 sku 不能为空。")
    dates = cleaned["date"].astype("string")
    parsed = pd.to_datetime(dates.where(dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)),
                            format="%Y-%m-%d", errors="coerce")
    if parsed.isna().any():
        errors.append("date 必须是有效的 YYYY-MM-DD 日历日期。")
    cleaned["date"] = parsed
    invalid_type = cleaned.demand.map(lambda x: isinstance(x, (bool, complex)))
    numeric = pd.to_numeric(cleaned.demand.astype(object).mask(invalid_type), errors="coerce")
    if numeric.isna().any() or not numeric.map(math.isfinite).all() or (numeric < 0).any():
        errors.append("demand 必须是非负有限数值，不能缺失或为布尔值。")
    cleaned["demand"] = numeric
    if cleaned.duplicated(["date", "sku"]).any():
        errors.append("同一 SKU 每个日期只能有一条日需求记录。")
    return ValidationResult(not errors, errors, [], cleaned if not errors else None)


def calculate_demand_statistics(df: pd.DataFrame, min_observations: int = 14) -> pd.DataFrame:
    if isinstance(min_observations, bool) or not isinstance(min_observations, int) or min_observations < 2:
        raise ValueError("最少观测数必须是至少为 2 的整数。")
    validated = validate_demand_history(df)
    if not validated.valid:
        raise ValueError("; ".join(validated.errors))
    rows = []
    for sku, group in validated.cleaned.groupby("sku", sort=True):
        n = len(group)
        start, end = group.date.min(), group.date.max()
        span = (end - start).days + 1
        row = dict(sku=sku, n_observations=n, span_days=span, missing_days=span - n,
                   start_date=start.date().isoformat(), end_date=end.date().isoformat(),
                   history_mean_daily_demand=float("nan"), daily_demand_std=float("nan"),
                   demand_cv=float("nan"), history_usable=False)
        if span != n:
            row.update(history_status="存在缺失日期", history_message="日期不连续，未将缺失日补为零；不能可靠计算日需求波动。")
        elif n < min_observations:
            row.update(history_status="观测不足", history_message=f"只有 {n} 个有效日观测，至少需要 {min_observations} 个。")
        else:
            try:
                values = group.demand.astype(float).tolist()
                average = float(mean(values))
                if average == 0:
                    row.update(history_mean_daily_demand=0.0, history_status="平均需求为零",
                               history_message="历史均值为零，标准差/CV 不用于策略估算；保留原固定策略。")
                else:
                    sigma = stdev(values)
                    cv = sigma / average
                    if not all(math.isfinite(x) for x in [average, sigma, cv]):
                        raise OverflowError
                    row.update(history_mean_daily_demand=average, daily_demand_std=sigma,
                               demand_cv=cv, history_usable=True, history_status="可用",
                               history_message="通过样本与连续性门槛；仍需检查季节性、趋势和数据时效。")
            except (OverflowError, ValueError):
                row.update(history_status="计算超出范围", history_message="统计量超出有限数值范围，保留固定策略。")
        rows.append(row)
    return pd.DataFrame(rows, columns=STAT_COLUMNS)
