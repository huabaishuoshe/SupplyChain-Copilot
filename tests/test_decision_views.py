from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def app(page):
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    at.radio(key="page_navigation").set_value(page).run()
    assert not at.exception
    return at


def upload_history(at, values=(2, 4, 6), sku="SKU-001"):
    df = pd.DataFrame(dict(date=pd.date_range("2026-01-01", periods=len(values)).strftime("%Y-%m-%d"), sku=sku, demand=values))
    next(w for w in at.get("file_uploader") if w.key.startswith("history_upload_")).set_value(
        ("user_history.csv", df.to_csv(index=False).encode(), "text/csv")).run()
    assert not at.exception
    return at


def test_demand_page_without_history_keeps_fixed_policy():
    at = app("需求波动与策略")
    assert any("没有可用历史时间序列" in info.value for info in at.info)
    at.selectbox(key="policy_selector").select("基于需求波动估算").run()
    assert not at.exception
    assert at.dataframe[-1].value.safety_stock_policy.eq("固定天数").all()
    assert at.dataframe[-1].value.recommended_reorder_qty.sum() == 50


def test_history_import_std_cv_policy_and_export_buttons():
    at = upload_history(app("需求波动与策略"))
    at.number_input(key="history_minimum").set_value(3).run()
    assert not at.exception
    stats = at.dataframe[0].value.iloc[0]
    assert stats.daily_demand_std == 2 and stats.demand_cv == .5
    comparison = at.dataframe[1].value
    row = comparison[comparison.sku == "SKU-001"].iloc[0]
    assert row.avg_daily_demand == 4
    assert row.safety_stock_fixed == 20
    assert row.variability_policy_applied == "需求波动"
    at.selectbox(key="policy_selector").select("基于需求波动估算").run()
    assert at.dataframe[-1].value.iloc[0].safety_stock_policy == "需求波动"
    assert len(at.get("download_button")) == 3
    at.get("download_button")[1].click().run()
    assert not at.exception


def test_history_insufficient_and_clear():
    at = upload_history(app("需求波动与策略"))
    assert pd.isna(at.dataframe[0].value.iloc[0].daily_demand_std)
    assert any("不满足波动估算条件" in warning.value for warning in at.warning)
    at.button(key="clear_history").click().run()
    assert "history_frame" not in at.session_state
    assert any("没有可用历史时间序列" in info.value for info in at.info)


def test_service_level_widget_changes_calculated_safety_stock():
    at = upload_history(app("需求波动与策略"))
    at.number_input(key="history_minimum").set_value(3).run()
    at.selectbox(key="policy_selector").select("基于需求波动估算").run()
    initial = at.dataframe[-1].value.iloc[0].safety_stock
    at.selectbox(key="service_level").set_value(.99).run()
    assert not at.exception
    assert at.dataframe[-1].value.iloc[0].safety_stock > initial
    assert "99.00%" in at.dataframe[-1].value.iloc[0].policy_note


def test_invalid_history_replaces_previous_without_using_stale_statistics():
    at = upload_history(app("需求波动与策略"))
    next(w for w in at.get("file_uploader") if w.key.startswith("history_upload_")).set_value(
        ("bad.csv", b"date,sku,demand\nwrong,SKU-001,-1\n", "text/csv")).run()
    assert not at.exception
    assert at.error
    assert "history_frame" not in at.session_state
    assert at.dataframe[-1].value.safety_stock_policy.eq("固定天数").all()


def test_history_persists_across_pages_and_dashboard_unaffected():
    at = upload_history(app("需求波动与策略"))
    at.number_input(key="history_minimum").set_value(3).run()
    at.radio(key="page_navigation").set_value("库存仪表盘").run()
    assert [m.value for m in at.metric] == ["4", "1", "50", "425.00"]
    assert at.dataframe[0].value.iloc[0].avg_daily_demand == 12
    at.radio(key="page_navigation").set_value("需求波动与策略").run()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0].history_usable


def test_scenario_adjustments_and_reset():
    at = app("情景分析")
    at.number_input(key="scenario_demand_pct").set_value(100.0).run()
    assert not at.exception
    summary = at.dataframe[0].value
    assert summary.loc["高风险 SKU 数", "调整后"] > summary.loc["高风险 SKU 数", "基准"]
    at.number_input(key="scenario_stock_pct").set_value(-50.0).run()
    at.number_input(key="scenario_lead_delta").set_value(3.0).run()
    at.checkbox(key="scenario_override_safety").check().run()
    at.number_input(key="scenario_safety_days").set_value(10.0).run()
    assert not at.exception
    assert at.dataframe[1].value.iloc[0].safety_stock_days_scenario == 10
    at.button(key="reset_scenario").click().run()
    assert not at.exception
    assert at.number_input(key="scenario_demand_pct").value == 0
    assert at.number_input(key="scenario_stock_pct").value == 0
    assert at.number_input(key="scenario_lead_delta").value == 0
    assert not at.checkbox(key="scenario_override_safety").value
    assert at.dataframe[0].value["变化"].eq(0).all()


def test_negative_adjusted_lead_time_shows_error():
    at = app("情景分析")
    at.number_input(key="scenario_lead_delta").set_value(-100.0).run()
    assert not at.exception
    assert any("负交期" in error.value for error in at.error)
    assert not at.dataframe


def test_supplier_page_without_field_is_usable():
    at = app("供应商分析")
    assert any("未提供 supplier 字段" in info.value for info in at.info)
    assert not at.error
    at.radio(key="page_navigation").set_value("情景分析").run()
    assert not at.exception and at.dataframe


def test_supplier_page_uses_actual_uploaded_groups():
    at = app("供应商分析")
    df = pd.read_csv(APP.parent / "sample_inventory.csv")
    df["supplier"] = ["虚构供应商 A", "虚构供应商 A", "虚构供应商 B", "虚构供应商 B"]
    at.get("file_uploader")[0].set_value(("suppliers.csv", df.to_csv(index=False).encode(), "text/csv")).run()
    assert not at.exception
    assert at.dataframe[0].value.sku_count.tolist() == [2, 2]
    assert at.dataframe[0].value.recommended_reorder_qty.tolist() == [50, 0]
