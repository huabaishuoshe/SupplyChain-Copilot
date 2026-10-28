import io
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def make_app():
    return AppTest.from_file(str(APP), default_timeout=20).run()


def upload_frame():
    return pd.DataFrame([dict(sku="CUSTOM-001", product_name="上传测试商品", current_stock=20,
                              avg_daily_demand=10, lead_time_days=5,
                              safety_stock_days=2, in_transit_stock=30)])


def test_default_dashboard_without_llm_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = make_app()
    assert not at.exception
    assert [metric.value for metric in at.metric] == ["4", "1", "50", "425.00"]
    assert len(at.dataframe[0].value) == 4
    assert any("无需 API Key" in info.value for info in at.info)


def test_risk_filter_and_detail():
    at = make_app()
    at.selectbox(key="risk_filter").select("高").run()
    assert not at.exception
    assert at.dataframe[0].value.sku.tolist() == ["SKU-002"]
    assert at.selectbox(key="detail_sku").value == "SKU-002"
    details = at.dataframe[1].value
    assert details.loc["recommended_reorder_qty", "数值"] == "50"


def test_sku_filter():
    at = make_app()
    at.multiselect(key="sku_filter").set_value(["SKU-004"]).run()
    assert not at.exception
    assert at.dataframe[0].value.sku.tolist() == ["SKU-004"]


def test_detail_selection_after_risk_filter_reset():
    at = make_app()
    at.selectbox(key="risk_filter").select("高").run()
    at.selectbox(key="risk_filter").select("全部").run()
    at.selectbox(key="detail_sku").select("SKU-004").run()
    assert not at.exception
    assert at.dataframe[1].value.loc["potential_overstock", "数值"] == "380.0"


@pytest.mark.parametrize("column", ["lead_time_days", "in_transit_stock"])
def test_blank_numeric_cell_in_uploaded_csv(column):
    at = make_app()
    df = upload_frame().astype(object)
    df.loc[0, column] = ""
    at.get("file_uploader")[0].set_value(("blank.csv", df.to_csv(index=False).encode(), "text/csv")).run()
    assert not at.exception
    assert any(column in error.value for error in at.error)
    assert not at.dataframe


def test_empty_filter_is_handled():
    at = make_app()
    at.selectbox(key="risk_filter").select("高")
    at.multiselect(key="sku_filter").set_value(["SKU-004"])
    at.run()
    assert not at.exception
    assert at.dataframe[0].value.empty
    assert at.get("download_button")[0].proto.disabled


@pytest.mark.parametrize("suffix", ["csv", "xlsx"])
def test_upload_and_sample_reset(suffix):
    at = make_app()
    df = upload_frame()
    if suffix == "csv":
        content = df.to_csv(index=False).encode("utf-8-sig")
    else:
        file = io.BytesIO()
        df.to_excel(file, index=False)
        content = file.getvalue()
    at.get("file_uploader")[0].set_value((f"upload.{suffix}", content, "application/octet-stream")).run()
    assert not at.exception
    assert at.dataframe[0].value.sku.tolist() == ["CUSTOM-001"]
    assert at.dataframe[0].value.iloc[0].recommended_reorder_qty == 20
    # Regression: previously a still-selected upload overrode this button.
    at.button[0].click().run()
    assert not at.exception
    assert len(at.dataframe[0].value) == 4
    assert at.get("file_uploader")[0].value is None
    at.selectbox(key="risk_filter").select("高").run()
    assert at.dataframe[0].value.sku.tolist() == ["SKU-002"]


def test_invalid_upload_stops_analysis():
    at = make_app()
    at.get("file_uploader")[0].set_value(("missing.csv", b"sku\nA", "text/csv")).run()
    assert not at.exception
    assert any("缺少必需列" in error.value for error in at.error)
    assert not at.dataframe
    assert not at.get("download_button")


def test_corrupt_upload_shows_read_error():
    at = make_app()
    at.get("file_uploader")[0].set_value(("bad.xlsx", b"broken", "application/octet-stream")).run()
    assert not at.exception
    assert any("文件读取失败" in error.value for error in at.error)


def test_legacy_xls_upload_in_ui():
    at = make_app()
    path = Path(__file__).parent / "fixtures" / "inventory.xls"
    at.get("file_uploader")[0].set_value((path.name, path.read_bytes(), "application/vnd.ms-excel")).run()
    assert not at.exception
    assert not at.error
    assert len(at.dataframe[0].value) == 4


def test_download_button_does_not_reset_filters():
    at = make_app()
    at.selectbox(key="risk_filter").select("高").run()
    at.get("download_button")[0].click().run()
    assert not at.exception
    assert at.selectbox(key="risk_filter").value == "高"
    assert at.dataframe[0].value.sku.tolist() == ["SKU-002"]
