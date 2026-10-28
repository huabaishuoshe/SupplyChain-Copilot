"""Create a fictional, distinct upload workbook for browser smoke checks."""

from pathlib import Path

import pandas as pd


root = Path(__file__).resolve().parents[1]
(root / "work").mkdir(exist_ok=True)
pd.DataFrame([dict(sku="CUSTOM-001", product_name="虚构上传商品", current_stock=20,
                   avg_daily_demand=10, lead_time_days=5, safety_stock_days=2,
                   in_transit_stock=30)]).to_excel(root / "work" / "browser_inventory.xlsx", index=False)
