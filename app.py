from pathlib import Path

import pandas as pd
import streamlit as st
from supplychain_copilot.calculations import analyze_inventory
from supplychain_copilot.file_io import export_inventory_csv, read_inventory_file
from supplychain_copilot.validation import REQUIRED_COLUMNS, validate_inventory
from supplychain_copilot.views import render_demand_analysis, render_scenarios, render_suppliers

st.set_page_config(page_title="SupplyChain Copilot", page_icon="📦", layout="wide")
st.title("📦 SupplyChain Copilot")
st.caption("库存计算由 Python 公式完成，AI 仅作为可选解释层。")

def sample_data():
    path = Path(__file__).resolve().parent / "sample_inventory.csv"
    return read_inventory_file(path.name, path.read_bytes())

st.session_state.setdefault("upload_revision", 0)
with st.sidebar:
    page = st.radio("功能页面", ["库存仪表盘", "需求波动与策略", "情景分析", "供应商分析"], key="page_navigation")
    use_sample = st.button("使用示例数据")
    if use_sample:
        # A new uploader key actually clears the old upload on this rerun.
        st.session_state["upload_revision"] += 1
    uploaded = st.file_uploader("上传 CSV 或 Excel", type=["csv", "xlsx", "xls"],
                                key=f"inventory_upload_{st.session_state['upload_revision']}")
    st.caption("必需列：" + ", ".join(REQUIRED_COLUMNS))
    st.caption("可选列：in_transit_stock（缺少时按 0 并提示）、supplier；Excel 读取第一个工作表，文件上限 20 MB。")

try:
    raw = read_inventory_file(uploaded.name, uploaded.getvalue()) if uploaded else sample_data()
except Exception as exc:
    st.error(f"文件读取失败：{exc}")
    st.stop()
st.caption(f"当前数据：{uploaded.name if uploaded else '虚构示例数据（非真实业务数据）'}")
validation = validate_inventory(raw)
with st.expander("数据质量检查", expanded=True):
    if validation.valid: st.success("数据质量检查通过")
    for e in validation.errors: st.error(e)
    for w in validation.warnings: st.warning(w)
if not validation.valid: st.stop()
if page != "库存仪表盘":
    {"需求波动与策略": render_demand_analysis, "情景分析": render_scenarios,
     "供应商分析": render_suppliers}[page](validation.cleaned)
    with st.expander("公式和使用假设"):
        st.markdown((Path(__file__).resolve().parent / "FORMULAS.md").read_text(encoding="utf-8"))
    st.info("当前版本未接入 LLM；无需 API Key。库存计算、筛选、详情和导出均可独立使用。")
    st.stop()
try:
    result = analyze_inventory(raw)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
selected = st.sidebar.selectbox("缺货风险", ["全部", "高", "中", "低", "无需求"], key="risk_filter")
view = result if selected == "全部" else result[result["stockout_risk"] == selected]
selected_skus = st.sidebar.multiselect("SKU 筛选（留空表示全部）", result["sku"].tolist(), key="sku_filter")
if selected_skus:
    view = view[view["sku"].isin(selected_skus)]
c1, c2, c3, c4 = st.columns(4)
c1.metric("SKU 数", len(view))
c2.metric("高风险 SKU", int((view["stockout_risk"] == "高").sum()))
c3.metric("建议补货总量", f"{view['recommended_reorder_qty'].sum():,.0f}")
c4.metric("潜在积压总量", f"{view['potential_overstock'].sum():,.2f}")
st.caption("指标、表格和导出均按当前筛选计算。跨 SKU 合计仅在数量单位一致时有业务意义。")
st.subheader("库存分析结果")
st.dataframe(view, width="stretch", hide_index=True, key="inventory_table")
st.download_button("导出分析 CSV", export_inventory_csv(view), "inventory_analysis.csv", "text/csv",
                   disabled=view.empty, key="export_csv")
if view.empty:
    st.info("当前筛选没有匹配 SKU，请调整筛选条件。")
else:
    st.subheader("风险分布")
    st.bar_chart(view["stockout_risk"].value_counts().rename("SKU 数"))
    st.subheader("SKU 详情")
    detail_sku = st.selectbox("选择 SKU 查看详情", view["sku"].tolist(), key="detail_sku")
    detail = view.loc[view["sku"] == detail_sku].iloc[0]
    st.dataframe(detail.astype(str).rename("数值").to_frame(), width="stretch", key="sku_details")
    st.write(f"交期需求 = {detail.avg_daily_demand:g} × {detail.lead_time_days:g} = {detail.lead_time_demand:g}")
    st.write(f"库存位置 = {detail.current_stock:g} + {detail.in_transit_stock:g} = {detail.inventory_position:g}")
    st.write(f"建议补货量 = ceil(max({detail.target_stock:g} - {detail.inventory_position:g}, 0)) = {detail.recommended_reorder_qty}")
    st.caption("缺货风险按现货覆盖天数判断。在途库存抵扣补货量，但因未提供到货日期，不用于降低缺货风险。")
with st.expander("公式和使用假设"):
    st.markdown((Path(__file__).resolve().parent / "FORMULAS.md").read_text(encoding="utf-8"))
st.info("当前版本未接入 LLM；无需 API Key。库存计算、筛选、详情和导出均可独立使用。")
