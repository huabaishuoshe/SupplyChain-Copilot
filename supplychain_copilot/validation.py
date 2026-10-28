from dataclasses import dataclass, field
import math
from typing import List
import pandas as pd

REQUIRED_COLUMNS = ["sku", "product_name", "current_stock", "avg_daily_demand", "lead_time_days", "safety_stock_days"]
NUMERIC_COLUMNS = ["current_stock", "avg_daily_demand", "lead_time_days", "safety_stock_days"]
OPTIONAL_COLUMNS = ["in_transit_stock"]

@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    cleaned: pd.DataFrame | None = None

def validate_inventory(df: pd.DataFrame) -> ValidationResult:
    if not isinstance(df, pd.DataFrame):
        return ValidationResult(False, ["输入必须是 pandas DataFrame。"])
    if df.columns.duplicated().any():
        return ValidationResult(False, ["列名不能重复。"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return ValidationResult(False, [f"缺少必需列: {', '.join(missing)}"])
    cleaned = df[REQUIRED_COLUMNS + [c for c in OPTIONAL_COLUMNS + ["supplier"] if c in df]].copy()
    errors, warnings = [], []
    if "in_transit_stock" not in cleaned:
        cleaned["in_transit_stock"] = 0.0
        warnings.append("未提供 in_transit_stock，按 0 计算；请确认是否有已下单未到货库存。")
    if cleaned.empty:
        errors.append("数据不能为空。")
    for col in ["sku", "product_name"]:
        cleaned[col] = cleaned[col].astype("string").str.strip()
        if cleaned[col].isna().any() or cleaned[col].eq("").any():
            errors.append(f"{col} 不能为空。")
    if cleaned["sku"].duplicated().any():
        errors.append("sku 必须唯一。")
    if "supplier" in cleaned:
        cleaned["supplier"] = cleaned["supplier"].astype("string").str.strip()
        if cleaned.supplier.isna().any() or cleaned.supplier.eq("").any():
            warnings.append("存在空供应商，供应商分析将归入“未填写供应商”，不丢弃对应库存。")
    for col in NUMERIC_COLUMNS + OPTIONAL_COLUMNS:
        # Booleans/complex numbers are not meaningful quantities, even though
        # pandas can coerce them to numbers. Reject infinity before arithmetic.
        invalid_type = cleaned[col].map(lambda value: isinstance(value, (bool, complex)))
        converted = pd.to_numeric(cleaned[col].astype(object).mask(invalid_type), errors="coerce")
        if converted.isna().any() or not converted.map(math.isfinite).all():
            errors.append(f"{col} 必须是数值且为有限实数，不能缺失（不接受布尔值、复数、NaN 或无穷大）。")
        if (converted < 0).any():
            errors.append(f"{col} 不能为负数。")
        cleaned[col] = converted
    if (cleaned["avg_daily_demand"] == 0).any():
        warnings.append("存在日均需求为 0 的 SKU，覆盖天数和补货量将按公式特殊处理。")
    return ValidationResult(not errors, errors, warnings, cleaned if not errors else None)
