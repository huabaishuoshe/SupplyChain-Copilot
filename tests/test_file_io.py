import io
from pathlib import Path

import pandas as pd
import pytest

from supplychain_copilot.calculations import analyze_inventory
from supplychain_copilot.file_io import MAX_FILE_BYTES, export_inventory_csv, read_inventory_file


def input_frame():
    return pd.DataFrame([dict(sku="001", product_name="虚构商品", current_stock=20,
                              avg_daily_demand=10, lead_time_days=5,
                              safety_stock_days=2, in_transit_stock=30)])


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030"])
def test_read_csv_preserves_sku(encoding):
    content = input_frame().to_csv(index=False).encode(encoding)
    result = read_inventory_file("inventory.csv", content)
    assert result.iloc[0].sku == "001"
    assert result.iloc[0].product_name == "虚构商品"
    assert analyze_inventory(result).iloc[0].recommended_reorder_qty == 20


def test_xlsx_upload():
    file = io.BytesIO()
    input_frame().to_excel(file, index=False, engine="openpyxl")
    result = analyze_inventory(read_inventory_file("inventory.XLSX", file.getvalue()))
    assert result.iloc[0].sku == "001"
    assert result.iloc[0].recommended_reorder_qty == 20


def test_real_legacy_xls_fixture():
    file = Path(__file__).parent / "fixtures" / "inventory.xls"
    result = analyze_inventory(read_inventory_file(file.name, file.read_bytes()))
    assert len(result) == 4
    assert result.loc[result.sku == "SKU-002", "recommended_reorder_qty"].iloc[0] == 50


def test_csv_roundtrip_with_zero_demand():
    data = input_frame()
    data.loc[0, "avg_daily_demand"] = 0
    result = analyze_inventory(data)
    payload = export_inventory_csv(result)
    assert payload.startswith(b"\xef\xbb\xbf")
    reread = pd.read_csv(io.BytesIO(payload), dtype={"sku": "string"})
    assert list(reread.columns) == list(result.columns)
    assert reread.iloc[0].sku == "001"
    assert pd.isna(reread.iloc[0].coverage_days)
    assert reread.iloc[0].recommended_reorder_qty == 0


def test_export_only_filtered_rows():
    result = analyze_inventory(pd.concat([input_frame(), input_frame().assign(sku="002")]))
    filtered = result[result.sku == "002"]
    csv = pd.read_csv(io.BytesIO(export_inventory_csv(filtered)), dtype={"sku": "string"})
    assert csv.sku.tolist() == ["002"]
    assert "Unnamed: 0" not in csv


@pytest.mark.parametrize("name,content", [("empty.csv", b""), ("data.txt", b"a,b"),
                                           ("bad.xlsx", b"not an Excel workbook"),
                                           ("bad.xls", b"not an Excel workbook")])
def test_invalid_files(name, content):
    with pytest.raises((ValueError, OSError)):
        read_inventory_file(name, content)


def test_oversized_file():
    with pytest.raises(ValueError, match="20 MB"):
        read_inventory_file("large.csv", b"x" * (MAX_FILE_BYTES + 1))


def test_duplicate_csv_headers():
    with pytest.raises(ValueError, match="列名不能重复"):
        read_inventory_file("duplicate.csv", b"sku,sku\nA,B")


def test_duplicate_excel_headers():
    file = io.BytesIO()
    pd.DataFrame([["A", "B"]], columns=["sku", "sku"]).to_excel(file, index=False)
    with pytest.raises(ValueError, match="列名不能重复"):
        read_inventory_file("duplicate.xlsx", file.getvalue())


def test_na_literal_sku_preserved():
    csv = input_frame().assign(sku="NA").to_csv(index=False).encode()
    assert analyze_inventory(read_inventory_file("data.csv", csv)).iloc[0].sku == "NA"
