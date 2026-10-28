"""Assert formulas in actual browser downloads of explicitly fictional test data."""

from pathlib import Path
from statistics import NormalDist
import math

import pandas as pd

output = Path(__file__).resolve().parents[1] / "outputs"
scenario = pd.read_csv(output / "decision_scenario_demand100.csv").set_index("sku")
assert scenario.loc["SKU-001", "coverage_days_scenario"] == 7.5
assert scenario.loc["SKU-001", "lead_time_demand_scenario"] == 240
assert scenario.loc["SKU-001", "projected_available_at_lead_end_scenario"] == -60
assert scenario.loc["SKU-001", "recommended_reorder_qty_scenario"] == 180
assert scenario.loc["SKU-001", "stockout_risk_scenario"] == "高"
reset = pd.read_csv(output / "decision_scenario_reset.csv")
for column in reset:
    if column.endswith("_baseline"):
        pd.testing.assert_series_equal(reset[column], reset[column.replace("_baseline", "_scenario")], check_names=False)
fixed = pd.read_csv(output / "decision_policy_comparison.csv").set_index("sku")
variable = pd.read_csv(output / "decision_variable_policy.csv").set_index("sku")
high_service = pd.read_csv(output / "decision_variable_policy99.csv").set_index("sku")
sigma = math.sqrt(56 / 13)  # 14 alternating explicit observations: 2,6,...
expected = NormalDist().inv_cdf(.95) * sigma * math.sqrt(10)
assert fixed.loc["SKU-001", "avg_daily_demand"] == 4
assert fixed.loc["SKU-001", "safety_stock_fixed"] == 20
assert math.isclose(variable.loc["SKU-001", "safety_stock"], expected, rel_tol=1e-12)
assert high_service.loc["SKU-001", "safety_stock"] > variable.loc["SKU-001", "safety_stock"]
assert math.isclose(high_service.loc["SKU-001", "safety_stock"], NormalDist().inv_cdf(.99) * sigma * math.sqrt(10), rel_tol=1e-12)
assert variable.loc["SKU-002", "safety_stock_policy"] == "固定天数"
suppliers = pd.read_csv(output / "decision_suppliers.csv").set_index("supplier")
assert suppliers.loc["FictionalSupplierA", "sku_count"] == 2
assert suppliers.loc["FictionalSupplierA", "high_risk_skus"] == 1
assert suppliers.loc["FictionalSupplierA", "recommended_reorder_qty"] == 60
assert suppliers.loc["FictionalSupplierB", "medium_risk_skus"] == 1
print("Downloaded scenario, reset, safety stock, service level and supplier calculations verified.")
