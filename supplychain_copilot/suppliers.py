"""Supplier grouping of current inventory; no delivery performance is inferred."""

import pandas as pd


def summarize_suppliers(result: pd.DataFrame) -> pd.DataFrame:
    if "supplier" not in result:
        return pd.DataFrame()
    source = result.copy(deep=True)
    source["supplier"] = source.supplier.astype("string").str.strip().replace("", pd.NA).fillna("未填写供应商")
    records = []
    for supplier, group in source.groupby("supplier", sort=True):
        row = dict(supplier=supplier, sku_count=group.sku.nunique(),
                   current_stock=group.current_stock.sum(), in_transit_stock=group.in_transit_stock.sum(),
                   inventory_position=group.inventory_position.sum(),
                   recommended_reorder_qty=sum(group.recommended_reorder_qty.tolist()),
                   potential_overstock=group.potential_overstock.sum())
        for label, column in [("高", "high_risk_skus"), ("中", "medium_risk_skus"),
                              ("低", "low_risk_skus"), ("无需求", "zero_demand_skus")]:
            row[column] = int(group.stockout_risk.eq(label).sum())
        records.append(row)
    return pd.DataFrame(records)
