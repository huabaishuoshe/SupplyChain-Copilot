"""Regenerate fictional Excel fixtures: python tests/generate_excel_fixtures.py."""

from pathlib import Path

import pandas as pd
import xlwt


def main():
    root = Path(__file__).resolve().parents[1]
    frame = pd.read_csv(root / "sample_inventory.csv", dtype={"sku": str})
    fixtures = root / "tests" / "fixtures"
    fixtures.mkdir(exist_ok=True)
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Inventory")
    for row_index, row in enumerate([frame.columns.tolist()] + frame.values.tolist()):
        for col_index, value in enumerate(row):
            sheet.write(row_index, col_index, value)
    workbook.save(str(fixtures / "inventory.xls"))
    outputs = root / "outputs"
    outputs.mkdir(exist_ok=True)
    frame.to_excel(outputs / "sample_inventory.xlsx", index=False)


if __name__ == "__main__":
    main()
