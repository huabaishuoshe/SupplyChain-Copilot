"""Additional Streamlit views; the original inventory dashboard stays default."""

import pandas as pd
import streamlit as st

from .calculations import analyze_inventory
from .demand import calculate_demand_statistics, validate_demand_history
from .file_io import export_inventory_csv, read_inventory_file
from .scenarios import ScenarioParameters, compare_scenarios
from .strategies import compare_inventory_policies
from .suppliers import summarize_suppliers


def render_demand_analysis(inventory):
    st.subheader("需求波动与库存策略")
    st.caption("只分析用户导入的逐日历史记录；不会根据平均销量生成历史或预测。未上传时保留固定天数策略。")
    st.download_button("下载空白历史销量模板", b"date,sku,demand\n", "demand_history_template.csv", "text/csv",
                       key="history_template")
    st.session_state.setdefault("history_revision", 0)
    if st.button("清除历史销量", key="clear_history"):
        st.session_state["history_revision"] += 1
        st.session_state.pop("history_frame", None)
        st.session_state.pop("history_filename", None)
        st.session_state.pop("history_errors", None)
    upload = st.file_uploader("可选历史销量 CSV", type=["csv"],
                              key=f"history_upload_{st.session_state['history_revision']}")
    st.caption("格式 date,sku,demand；日期 YYYY-MM-DD，每 SKU 每日一条。真实零需求日需显式填 0，缺失日不会补零。")
    if upload:
        st.session_state.pop("history_frame", None)
        try:
            frame = read_inventory_file(upload.name, upload.getvalue())
            checked = validate_demand_history(frame)
            if checked.valid:
                st.session_state["history_frame"] = frame.copy(deep=True)
                st.session_state["history_filename"] = upload.name
                st.session_state.pop("history_errors", None)
            else:
                st.session_state["history_errors"] = checked.errors
        except Exception as exc:
            st.session_state["history_errors"] = [f"历史文件读取失败：{exc}"]
    for error in st.session_state.get("history_errors", []):
        st.error(error)
    minimum = st.number_input("最少连续日观测数", min_value=2, max_value=3650,
                              value=st.session_state.get("saved_history_minimum", 14), step=1, key="history_minimum")
    st.session_state["saved_history_minimum"] = minimum
    level = st.selectbox("周期服务水平假设", [.90, .95, .975, .99], index=1,
                         format_func=lambda x: f"{x:.1%}", key="service_level")
    st.caption("服务水平是正态近似下的单侧周期无缺货假设，不是实际满足率。前提为独立同分布日需求、确定交期、无强趋势/季节性。")
    stats = None
    if "history_frame" in st.session_state:
        st.caption(f"当前历史来源：{st.session_state['history_filename']}（用户导入，跨页面保留，使用清除按钮移除）")
        stats = calculate_demand_statistics(st.session_state["history_frame"], int(minimum))
        st.dataframe(stats, width="stretch", hide_index=True, key="demand_statistics")
        invalid = int((~stats.history_usable).sum())
        if invalid:
            st.warning(f"{invalid} 个历史 SKU 不满足波动估算条件，统计量及原因见表；匹配的库存 SKU 将回退固定天数策略。")
        unmatched = set(stats.sku) - set(inventory.sku)
        if unmatched:
            st.warning("以下历史 SKU 不在当前库存中，不参与策略计算：" + ", ".join(sorted(unmatched)))
        st.warning("历史统计仅代表上传窗口；请核对窗口日期和数据时效。达到观测数门槛不代表已经验证预测可靠性。")
    else:
        st.info("没有可用历史时间序列，无法计算真实需求标准差/CV；继续使用固定安全库存天数。")

    selected = st.selectbox("安全库存策略", ["固定安全库存天数", "基于需求波动估算"], key="policy_selector")
    try:
        fixed, variable = compare_inventory_policies(inventory, stats, float(level))
    except ValueError as exc:
        st.error(str(exc))
        return
    st.subheader("策略对比（相同需求口径）")
    st.caption("匹配且可用的历史 SKU，两种策略都使用历史均值；其余均使用库存输入日均需求。此页不改变原库存仪表盘。")
    comparison = fixed[["sku", "avg_daily_demand", "demand_source"]].copy()
    for field in ["safety_stock", "target_stock", "recommended_reorder_qty", "stockout_risk"]:
        comparison[f"{field}_fixed"] = fixed[field].to_numpy()
        comparison[f"{field}_variability"] = variable[field].to_numpy()
    comparison["variability_policy_applied"] = variable.safety_stock_policy.to_numpy()
    comparison["reason"] = variable.policy_note.to_numpy()
    st.dataframe(comparison, width="stretch", hide_index=True, key="policy_comparison")
    st.download_button("导出策略对比 CSV", export_inventory_csv(comparison), "policy_comparison.csv", "text/csv", key="export_policies")
    chosen = variable if selected == "基于需求波动估算" else fixed
    st.subheader("当前选择策略的计算结果")
    if selected == "基于需求波动估算":
        fallbacks = int(chosen.safety_stock_policy.eq("固定天数").sum())
        if fallbacks:
            st.warning(f"{fallbacks} 个库存 SKU 已明确回退固定天数策略，请查看 policy_note。")
    st.dataframe(chosen, width="stretch", hide_index=True, key="chosen_policy")
    st.download_button("导出当前策略 CSV", export_inventory_csv(chosen), "selected_policy.csv", "text/csv", key="export_chosen_policy")
    st.caption(f"当前结果：需求波动策略 {int(chosen.safety_stock_policy.eq('需求波动').sum())} 个 SKU；固定天数策略 {int(chosen.safety_stock_policy.eq('固定天数').sum())} 个 SKU。")
    st.caption(f"当前服务水平假设：{level:.1%}。")


SCENARIO_DEFAULTS = {"scenario_demand_pct": 0.0, "scenario_lead_delta": 0.0,
                     "scenario_stock_pct": 0.0, "scenario_override_safety": False, "scenario_safety_days": 5.0}


def reset_scenario():
    for key, value in SCENARIO_DEFAULTS.items():
        st.session_state[key] = value


def render_scenarios(inventory):
    st.subheader("情景分析")
    st.caption("以原始库存输入和固定安全库存天数策略作基准。所有调整只作用于副本，不改写上传数据，也不把人为交期调整当成真实延迟率。")
    for key, value in SCENARIO_DEFAULTS.items():
        st.session_state.setdefault(key, value)
    st.button("恢复默认参数", key="reset_scenario", on_click=reset_scenario)
    left, right = st.columns(2)
    with left:
        demand = st.number_input("需求变化比例 (%)", min_value=-100.0, max_value=1000.0, step=10.0, key="scenario_demand_pct")
        lead = st.number_input("供应商交期变化天数", min_value=-3650.0, max_value=3650.0, step=1.0, key="scenario_lead_delta")
    with right:
        stock = st.number_input("当前库存变化比例 (%)", min_value=-100.0, max_value=1000.0, step=10.0, key="scenario_stock_pct")
        override = st.checkbox("统一覆盖安全库存天数", key="scenario_override_safety")
        safety = st.number_input("情景安全库存天数", min_value=0.0, max_value=3650.0, step=1.0,
                                 key="scenario_safety_days", disabled=not override)
    st.caption("关闭安全天数覆盖时，各 SKU 保留各自原天数。调整后任何交期为负将拒绝计算，不会自动截断为 0。")
    try:
        compared = compare_scenarios(inventory, ScenarioParameters(float(demand), float(lead), float(stock),
                                                                  float(safety) if override else None))
    except ValueError as exc:
        st.error(str(exc))
        return
    st.subheader("基准与调整后汇总")
    st.dataframe(compared.summary, width="stretch", key="scenario_summary")
    st.caption("高/中风险为标签计数；潜在积压 SKU 数为积压数量>0的行数；补货总量为逐 SKU 向上取整结果之和。单位不一致的数量不宜相加。")
    st.subheader("逐 SKU 对比")
    st.dataframe(compared.detail, width="stretch", hide_index=True, key="scenario_details")
    st.caption("coverage_days=现货/日均需求（零需求留空）；lead_time_demand=日均需求×交期；projected_available_at_lead_end=现货−交期需求，可为负表示缺口；忽略在途到货时点和新订单。")
    st.download_button("导出情景对比 CSV", export_inventory_csv(compared.detail), "scenario_comparison.csv", "text/csv", key="export_scenario")
    safety_label = f"{safety:g} 天" if override else "保留各 SKU 原值"
    st.caption(f"情景参数：需求 {demand:+g}%，交期 {lead:+g} 天，现货 {stock:+g}%，安全天数 {safety_label}。")


def render_suppliers(inventory):
    st.subheader("供应商分析")
    st.caption("按全部原库存数据、上传日均需求及固定天数策略汇总。没有采购订单历史，不计算准时交付率或实际延迟率。")
    result = analyze_inventory(inventory)
    summary = summarize_suppliers(result)
    if summary.empty:
        st.info("未提供 supplier 字段，无法按供应商分组。其他库存、历史需求与情景功能仍可使用。")
        return
    st.dataframe(summary, width="stretch", hide_index=True, key="supplier_summary")
    risk_columns = ["high_risk_skus", "medium_risk_skus", "low_risk_skus", "zero_demand_skus"]
    st.bar_chart(summary.set_index("supplier")[risk_columns].rename(columns={
        "high_risk_skus": "高", "medium_risk_skus": "中", "low_risk_skus": "低", "zero_demand_skus": "无需求"}))
    st.caption("sku_count 为各组唯一 SKU 数；现货、在途、库存位置和补货数量均为组内求和。跨 SKU 数量汇总仅在单位一致时有业务意义。")
    st.download_button("导出供应商汇总 CSV", export_inventory_csv(summary), "supplier_summary.csv", "text/csv", key="export_suppliers")
