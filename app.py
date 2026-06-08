import streamlit as st
import pandas as pd
import base64
import json
from datetime import datetime, date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import io
from PIL import Image

from data_generator import (
    BUSINESS_DISTRICTS, WEATHER_TYPES, TIME_SLOTS,
    generate_business_context, generate_hotspot_data,
    generate_rider_data, generate_timeout_data,
    generate_weather_data, detect_peak_warning,
    generate_subsidy_suggestion, get_district_responsible,
    get_all_district_responsibles
)
from warning_engine import (
    WARNING_DIMENSIONS, WARNING_LEVELS, DEFAULT_THRESHOLDS,
    get_effective_thresholds, detect_peak_warning_enhanced,
    generate_full_snapshot, simulate_post_resolution_state,
    create_acceptance_scenario
)
from log_manager import (
    log_subsidy_operation, record_peak_warning,
    record_peak_warning_full, save_acceptance_snapshot,
    get_operation_logs, get_peak_warnings, query_peak_warnings,
    get_peak_warning_by_id, get_acceptance_snapshots,
    logs_to_dataframe, warnings_to_dataframe, snapshots_to_dataframe,
    clear_all_warnings
)

st.set_page_config(
    page_title="外卖商圈骑手供需分析看板 · 峰值预警系统",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛵 外卖商圈骑手供需分析看板")
st.markdown("### 峰值预警 · 全链路回放系统")
st.markdown("---")

with st.sidebar:
    st.header("📋 业务上下文设置")
    st.caption("所有模块共享同一上下文，参数变更会联动更新全部数据")

    selected_date = st.date_input("选择日期", value=date.today())
    district = st.selectbox("选择商圈", BUSINESS_DISTRICTS, index=1)
    weather = st.selectbox("天气状况", WEATHER_TYPES, index=2)
    time_slot = st.selectbox("分析时段", TIME_SLOTS, index=2)

    st.markdown("---")
    st.info(f"📍 当前商圈责任人：**{get_district_responsible(district)}**")

    st.markdown("---")
    operator = st.text_input("操作人", value="调度员A")

    refresh_btn = st.button("🔄 刷新数据（基于当前上下文）", use_container_width=True, type="primary")

    with st.expander("📋 全部商圈责任人一览"):
        responsibles = get_all_district_responsibles()
        for d, r in responsibles.items():
            st.markdown(f"- **{d}**：{r}")

    st.markdown("---")
    st.markdown("### ⚙️ 预警阈值配置")
    with st.expander("🔧 四维阈值（支持动态调整）", expanded=False):
        st.caption("供需比与超时率支持按时段动态调整")
        custom_thresholds = json.loads(json.dumps(DEFAULT_THRESHOLDS))
        for dim in WARNING_DIMENSIONS:
            st.markdown(f"**{dim}**")
            c1, c2 = st.columns(2)
            with c1:
                warn_key = f"th_warn_{dim}"
                crit_key = f"th_crit_{dim}"
                default_warn = DEFAULT_THRESHOLDS[dim]["warning"]
                default_crit = DEFAULT_THRESHOLDS[dim]["critical"]
                if dim == "超时率":
                    custom_thresholds[dim]["warning"] = float(st.number_input(
                        f"{dim}-预警(%)",
                        value=float(default_warn * 100), min_value=1.0, max_value=50.0, step=1.0,
                        key=warn_key)) / 100.0
                    custom_thresholds[dim]["critical"] = float(st.number_input(
                        f"{dim}-严重(%)",
                        value=float(default_crit * 100), min_value=1.0, max_value=50.0, step=1.0,
                        key=crit_key)) / 100.0
                elif dim == "供需比":
                    custom_thresholds[dim]["warning"] = float(st.number_input(
                        f"{dim}-预警",
                        value=float(default_warn), min_value=1.0, max_value=30.0, step=0.5,
                        key=warn_key))
                    custom_thresholds[dim]["critical"] = float(st.number_input(
                        f"{dim}-严重",
                        value=float(default_crit), min_value=1.0, max_value=50.0, step=0.5,
                        key=crit_key))
                elif dim == "骑手负载均衡度":
                    custom_thresholds[dim]["warning"] = int(st.number_input(
                        f"{dim}-预警(单量差)",
                        value=int(default_warn), min_value=1, max_value=30, step=1,
                        key=warn_key))
                    custom_thresholds[dim]["critical"] = int(st.number_input(
                        f"{dim}-严重(单量差)",
                        value=int(default_crit), min_value=1, max_value=50, step=1,
                        key=crit_key))
                else:
                    custom_thresholds[dim]["warning"] = float(st.number_input(
                        f"{dim}-预警",
                        value=float(default_warn), min_value=1.0, max_value=3.0, step=0.1,
                        key=warn_key))
                    custom_thresholds[dim]["critical"] = float(st.number_input(
                        f"{dim}-严重",
                        value=float(default_crit), min_value=1.0, max_value=5.0, step=0.1,
                        key=crit_key))

    st.markdown("---")
    st.markdown("### 🧪 验收场景快速触发")
    with st.expander("🎯 一键触发三种预警场景", expanded=False):
        st.caption("点击按钮可自动生成场景数据并写入最终预警记录")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("📈 场景1：订单激增", use_container_width=True, key="btn_s1"):
                st.session_state.trigger_scenario = "供需比预警"
        with col_s2:
            if st.button("⏱️ 场景2：超时攀升", use_container_width=True, key="btn_s2"):
                st.session_state.trigger_scenario = "超时率预警"
        if st.button("🌧️ 场景3：恶劣天气+高峰复合预警", use_container_width=True, key="btn_s3"):
            st.session_state.trigger_scenario = "多维度复合预警"

if "trigger_scenario" not in st.session_state:
    st.session_state.trigger_scenario = None

if st.session_state.trigger_scenario:
    scenario = st.session_state.trigger_scenario
    ctx_s, hs_s, rd_s, to_s, wt_s = create_acceptance_scenario(scenario)
    wi_s = detect_peak_warning_enhanced(ctx_s, hs_s, rd_s, to_s, wt_s, custom_thresholds)
    snap_s = generate_full_snapshot(ctx_s, hs_s, rd_s, to_s, wt_s)
    pr_ctx, pr_hs, pr_rd, pr_to, pr_wt = simulate_post_resolution_state(ctx_s, hs_s, rd_s, to_s, wt_s)
    pr_snap = generate_full_snapshot(pr_ctx, pr_hs, pr_rd, pr_to, pr_wt)
    rec_s = record_peak_warning_full(wi_s, ctx_s, snap_s, pr_snap, scenario_tag=scenario)
    st.success(f"✅ {scenario}触发成功！记录ID：{rec_s['record_id']}")
    st.session_state.trigger_scenario = None
    st.rerun()

if refresh_btn or "context" not in st.session_state:
    context = generate_business_context(
        selected_date=selected_date,
        district=district,
        weather=weather,
        time_slot=time_slot
    )
    st.session_state.context = context
    st.session_state.hotspot = generate_hotspot_data(context)
    st.session_state.rider = generate_rider_data(context)
    st.session_state.timeout = generate_timeout_data(context)
    st.session_state.weather_data = generate_weather_data(context)
    st.session_state.warning = detect_peak_warning(
        context, st.session_state.hotspot, st.session_state.rider, st.session_state.timeout
    )
    st.session_state.warning_enhanced = detect_peak_warning_enhanced(
        context, st.session_state.hotspot, st.session_state.rider, st.session_state.timeout, st.session_state.weather_data, custom_thresholds
    )
    st.session_state.subsidy = generate_subsidy_suggestion(context, st.session_state.warning)
else:
    context = st.session_state.context

ctx = st.session_state.context
hotspot_wrapper = st.session_state.hotspot
hotspot_df = hotspot_wrapper["data"]
hotspot_version = hotspot_wrapper["version_trace"]
hotspot_summary = hotspot_wrapper["summary"]
rider_data = st.session_state.rider
timeout_data = st.session_state.timeout
weather_data = st.session_state.weather_data
warning_info = st.session_state.warning
warning_enhanced = st.session_state.warning_enhanced
subsidy_info = st.session_state.subsidy

st.markdown("### 📍 当前业务上下文")
col_ctx1, col_ctx2, col_ctx3, col_ctx4, col_ctx5, col_ctx6 = st.columns(6)
with col_ctx1:
    st.metric("商圈", ctx["district"])
with col_ctx2:
    peak_label = "⭐高峰期" if ctx["is_peak"] else ""
    st.metric("时段", f"{ctx['time_slot']} {peak_label}")
with col_ctx3:
    st.metric("天气", f"{ctx['weather']} (系数x{ctx['weather_factor']})")
with col_ctx4:
    level_color = {"严重": "🔴", "警告": "🟡", "正常": "🟢"}
    warn_level = warning_info["预警级别"]
    st.metric("预警级别", f"{level_color.get(warn_level, '')} {warn_level}")
with col_ctx5:
    sd_ratio = warning_info["供需比"]
    st.metric("供需比", f"{sd_ratio} 单/骑手")
with col_ctx6:
    st.metric("责任人", get_district_responsible(ctx["district"]))

effective_th = get_effective_thresholds(ctx, custom_thresholds)

rider_anomaly_info = rider_data.get("异常检测", {})
if rider_anomaly_info.get("是否异常"):
    st.error(
        f"⚠️ 检测到骑手在线异常（{rider_anomaly_info['异常数量']}项），"
        f"当前责任人：**{rider_anomaly_info['当前责任人']} —— "
        f"{rider_anomaly_info['责任人联系建议']}"
    )

st.markdown("---")

tab_hotspot, tab_rider, tab_timeout, tab_weather, tab_warning_list, tab_playback, tab_operation = st.tabs([
    "🔥 订单热区", "👥 骑手在线", "⏱️ 超时率", "🌦️ 天气影响",
    "⚠️ 预警记录列表", "🎬 预警回放与对比", "📝 操作与记录"
])

with tab_hotspot:
    st.subheader("订单热区分布")
    st.caption("基于当前业务上下文实时计算，包含版本痕迹追踪")

    with st.expander("🔍 数据版本痕迹与摘要", expanded=False):
        col_v1, col_v2, col_v3 = st.columns(3)
        with col_v1:
            st.markdown("**版本信息**")
            st.markdown(f"- Schema 版本：`{hotspot_version['schema_version']}`")
            st.markdown(f"- 数据类型：`{hotspot_version['data_type']}`")
            st.markdown(f"- 生成时间：`{hotspot_version['generated_at']}`")
            st.markdown(f"- 版本签名：`{hotspot_version['version_signature']}`")
        with col_v2:
            st.markdown("**上下文摘要**")
            for k, v in hotspot_version["context_digest"].items():
                st.markdown(f"- {k}：`{v}`")
        with col_v3:
            st.markdown("**热区统计摘要**")
            for k, v in hotspot_summary.items():
                st.markdown(f"- {k}：`{v}`")

    col_h1, col_h2 = st.columns([1, 1])
    with col_h1:
        fig_hotspot = px.bar(
            hotspot_df, x="子区域", y="订单量",
            color="热区等级",
            color_discrete_map={"低负荷": "#2ecc71", "正常": "#f1c40f", "高热区": "#e74c3c"},
            title="各子区域订单量与热区等级",
            text="订单量",
            hover_data=["所属商圈", "配属骑手数", "供需比", "责任人"]
        )
        st.plotly_chart(fig_hotspot, use_container_width=True)

    with col_h2:
        fig_supply = px.scatter(
            hotspot_df, x="供需比", y="订单量", size="商户密度",
            color="热区等级", hover_data=["子区域", "预计送达时长(分钟)", "配属骑手数", "责任人"],
            color_discrete_map={"低负荷": "#2ecc71", "正常": "#f1c40f", "高热区": "#e74c3c"},
            title="供需比 vs 订单量（气泡大小=商户密度）"
        )
        st.plotly_chart(fig_supply, use_container_width=True)

    st.dataframe(hotspot_df, use_container_width=True, hide_index=True)

with tab_rider:
    st.subheader("骑手在线状态")
    st.caption("与订单热区共享同一上下文，包含异常检测与责任人信息")

    rider_anomaly = rider_data.get("异常检测", {})
    rider_version = rider_data.get("version_trace", {})

    if rider_anomaly.get("是否异常"):
        st.error(f"🚨 骑手在线异常警报 —— 当前责任人：**{rider_anomaly['当前责任人']}")
        with st.expander("📋 异常详情与处置建议", expanded=True):
            for idx, anomaly in enumerate(rider_anomaly["异常列表"], 1):
                severity_icon = "🔴" if anomaly["严重程度"] == "高危" else "🟡"
                st.markdown(
                    f"{severity_icon} **异常 {idx}：{anomaly['异常类型']}**  "
                    f"（严重程度：{anomaly['严重程度']}）  \n"
                    f"描述：{anomaly['异常描述']}  \n"
                    f"建议动作：{anomaly['建议动作']}"
                )
    else:
        st.success("✅ 骑手在线状态正常，未检测到异常")

    col_r1, col_r2, col_r3, col_r4, col_r5, col_r6 = st.columns(6)
    with col_r1:
        st.metric("总注册骑手", rider_data["总注册骑手"])
    with col_r2:
        st.metric("在线骑手", rider_data["在线骑手"])
    with col_r3:
        st.metric("配送中骑手", rider_data["配送中骑手"])
    with col_r4:
        st.metric("空闲骑手", rider_data["空闲骑手"])
    with col_r5:
        st.metric("人均配送单量", f"{rider_data['人均配送单量']}单")
    with col_r6:
        st.metric("在线率", f"{rider_data['在线率(%)']}%")

    col_r5, col_r6 = st.columns([1, 1])
    with col_r5:
        fig_rider_pie = px.pie(
            rider_data["骑手状态分布"],
            names="状态", values="人数",
            title="骑手状态分布",
            color_discrete_sequence=["#e74c3c", "#3498db", "#95a5a6"],
            hover_data=["占比(%)"]
        )
        st.plotly_chart(fig_rider_pie, use_container_width=True)

    with col_r6:
        fig_rider_trend = go.Figure()
        fig_rider_trend.add_trace(go.Scatter(
            x=rider_data["近期趋势"]["时间点"],
            y=rider_data["近期趋势"]["在线骑手数"],
            mode="lines+markers", name="在线骑手", line=dict(color="#3498db")
        ))
        fig_rider_trend.add_trace(go.Scatter(
            x=rider_data["近期趋势"]["时间点"],
            y=rider_data["近期趋势"]["配送中骑手数"],
            mode="lines+markers", name="配送中骑手", line=dict(color="#e74c3c")
        ))
        fig_rider_trend.add_trace(go.Scatter(
            x=rider_data["近期趋势"]["时间点"],
            y=rider_data["近期趋势"]["空闲骑手数"],
            mode="lines+markers", name="空闲骑手", line=dict(color="#2ecc71"),
            fill="tonexty"
        ))
        fig_rider_trend.update_layout(title="近期骑手在线趋势")
        st.plotly_chart(fig_rider_trend, use_container_width=True)

    st.dataframe(rider_data["骑手状态分布"], use_container_width=True, hide_index=True)

with tab_timeout:
    st.subheader("超时率分析")

    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        st.metric("总订单数", timeout_data["总订单数"])
    with col_t2:
        st.metric("超时订单数", timeout_data["超时订单数"])
    with col_t3:
        rate_val = timeout_data["超时率(%)"]
        delta = f"{round(rate_val - 8, 2)}% vs 阈值"
        st.metric("超时率", f"{rate_val}%", delta=delta, delta_color="inverse")
    with col_t4:
        status = "🔴 超标" if timeout_data["是否超标"] else "🟢 正常"
        st.metric("判定结果", status)

    col_t5, col_t6 = st.columns([1, 1])
    with col_t5:
        fig_timeout_reason = px.bar(
            timeout_data["超时原因分布"], x="原因", y="订单数",
            color="占比(%)", title="超时原因分布", text="订单数"
        )
        st.plotly_chart(fig_timeout_reason, use_container_width=True)

    with col_t6:
        fig_timeout_trend = px.line(
            timeout_data["近7日趋势"], x="日期", y="超时率(%)",
            title="近7日超时率趋势", markers=True
        )
        fig_timeout_trend.add_hline(y=8, line_dash="dash", line_color="red",
                                      annotation_text="阈值 8%")
        st.plotly_chart(fig_timeout_trend, use_container_width=True)

    st.dataframe(timeout_data["超时原因分布"], use_container_width=True, hide_index=True)

with tab_weather:
    st.subheader("天气影响分析")

    impact = weather_data["影响摘要"]
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        st.metric("当前天气", impact["当前天气"])
    with col_w2:
        st.metric("影响系数", f"x{impact['影响系数']}")
    with col_w3:
        st.metric("影响等级", impact["影响等级"])

    col_w4, col_w5, col_w6 = st.columns(3)
    with col_w4:
        st.metric("订单增量预估", impact["订单增量预估"])
    with col_w5:
        st.metric("配送时长增加", impact["配送时长增加"])
    with col_w6:
        st.metric("骑手供给建议", impact["骑手供给建议"])

    st.markdown("#### 各类天气影响对比")
    st.dataframe(weather_data["天气对比表"], use_container_width=True, hide_index=True)

    st.markdown("#### 分时段天气影响")
    fig_weather = px.bar(
        weather_data["分时段影响"], x="时段", y=["天气影响订单量", "天气影响超时率(%)"],
        barmode="group", title="分时段天气影响趋势"
    )
    st.plotly_chart(fig_weather, use_container_width=True)

with tab_warning_list:
    st.subheader("⚠️ 峰值预警最终记录列表")
    st.caption("支持按商圈、时间、严重等级进行筛选，每条记录包含全景快照可回放")

    st.markdown("#### 🔍 筛选条件")
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        filter_district = st.selectbox("按商圈筛选", ["全部"] + BUSINESS_DISTRICTS, key="flt_dist")
    with col_f2:
        filter_level = st.selectbox("按等级筛选", ["全部", "严重", "警告", "正常"], key="flt_lvl")
    with col_f3:
        filter_scenario = st.selectbox("按场景筛选", ["全部", "供需比预警", "超时率预警", "多维度复合预警"], key="flt_scn")
    with col_f4:
        today = date.today()
        date_range = st.date_input("时间范围", value=(today - timedelta(days=7), today), key="flt_date")

    q_dist = None if filter_district == "全部" else filter_district
    q_level = None if filter_level == "全部" else filter_level
    q_scenario = None if filter_scenario == "全部" else filter_scenario
    q_start = None
    q_end = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        q_start = date_range[0].isoformat() + "T00:00:00"
        q_end = date_range[1].isoformat() + "T23:59:59"

    filtered_records = query_peak_warnings(
        district=q_dist, warning_level=q_level,
        start_time=q_start, end_time=q_end,
        scenario_tag=q_scenario
    )

    st.markdown(f"共 **{len(filtered_records)}** 条预警记录")

    filtered_df = warnings_to_dataframe(filtered_records)
    if filtered_df.empty:
        st.info("暂无预警记录，请先触发预警或使用左侧验收场景按钮")
    else:
        display_cols = ["时间", "预警级别", "商圈", "时段", "天气", "是否高峰期", "供需比", "触发维度", "可回放", "可对比", "场景标签"]
        st.dataframe(filtered_df[display_cols], use_container_width=True, hide_index=True)

    st.markdown("---")
    col_op1, col_op2, col_op3 = st.columns([1, 1, 1])
    with col_op1:
        if st.button("📝 将当前上下文生成全景快照预警", use_container_width=True):
            curr_snap = generate_full_snapshot(ctx, hotspot_wrapper, rider_data, timeout_data, weather_data)
            pr_ctx, pr_hs, pr_rd, pr_to, pr_wt = simulate_post_resolution_state(
                ctx, hotspot_wrapper, rider_data, timeout_data, weather_data
            )
            pr_snap = generate_full_snapshot(pr_ctx, pr_hs, pr_rd, pr_to, pr_wt)
            rec = record_peak_warning_full(
                warning_enhanced, ctx, curr_snap, pr_snap, scenario_tag="手动触发"
            )
            st.success(f"✅ 已记录全景预警，ID：{rec['record_id']}")
            st.rerun()
    with col_op2:
        if st.button("🧹 清空所有预警记录", use_container_width=True):
            clear_all_warnings()
            st.success("✅ 已清空所有预警记录")
            st.rerun()
    with col_op3:
        st.caption("提示：点击左侧验收场景按钮可快速触发三种验收预警")

    st.markdown("---")
    if filtered_records:
        st.markdown("### 📊 预警维度检测详情（当前上下文）")
        with st.expander("🔬 四维阈值命中详情", expanded=True):
            dim_df_list = []
            for dim in WARNING_DIMENSIONS:
                detail = warning_enhanced["维度检测详情"][dim]
                level = "正常"
                for hit in warning_enhanced["阈值命中详情"]:
                    if hit["dimension"] == dim:
                        level = hit["hit_level"]
                dim_df_list.append({
                    "监测维度": dim,
                    "当前值": detail["当前值"],
                    "预警阈值": detail["预警阈值"],
                    "严重阈值": detail["严重阈值"],
                    "动态阈值": "是" if detail["是否动态阈值"] else "否",
                    "时段系数": detail["时段调整系数"],
                    "命中等级": level
                })
            st.dataframe(pd.DataFrame(dim_df_list), use_container_width=True, hide_index=True)


def _render_snapshot_panel(snap, mode="warning"):
    if snap:
        ctx_s = snap.get("business_context", {})
        dims = snap.get("dimension_values", {})
        level = snap.get("overall_warning_level", "正常")

        c1, c2, c3, c4 = st.columns(4)
        level_icon = {"严重": "🔴", "警告": "🟡", "正常": "🟢"}.get(level, "⚪")
        with c1:
            st.metric("商圈", ctx_s.get("district", ""))
        with c2:
            st.metric("时段", ctx_s.get("time_slot", ""))
        with c3:
            st.metric("天气", f"{ctx_s.get('weather', '')} x{ctx_s.get('weather_factor', '')}")
        with c4:
            st.metric("预警等级", f"{level_icon} {level}")

        st.markdown("##### 📊 四维指标")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            sd = dims.get("供需比", 0)
            st.metric("供需比", f"{sd} 单/骑手")
        with m2:
            tr = dims.get("超时率", 0)
            st.metric("超时率", f"{round(tr * 100, 2)}%")
        with m3:
            lb = dims.get("骑手负载均衡度", 0)
            st.metric("负载单量差", f"{lb} 单")
        with m4:
            ws = dims.get("天气恶劣指数", 0)
            st.metric("天气指数", f"x{ws}")

        st.markdown("##### 🔥 订单热区图像")
        img_b64 = snap.get("hotspot_image_base64", "")
        if img_b64:
            try:
                img_bytes = base64.b64decode(img_b64)
                st.image(img_bytes, use_column_width=True, caption=f"{ctx_s.get('district', '')} 热区分布图")
            except Exception:
                st.warning("热区图像解码失败")
        else:
            st.info("无热区图像")

        modules = snap.get("modules_state", {})

        st.markdown("##### 👥 骑手分布点位")
        rider_pts = snap.get("rider_distribution_points", [])
        if rider_pts:
            rider_df = pd.DataFrame(rider_pts)
            if not rider_df.empty:
                fig_rider_map = px.scatter(
                    rider_df, x="x", y="y", color="status",
                    hover_data=["rider_id", "sub_area", "current_orders"],
                    title=f"骑手分布（共{len(rider_pts)}人）",
                    color_discrete_map={"配送中": "#e74c3c", "空闲": "#2ecc71", "取餐中": "#f1c40f"}
                )
                st.plotly_chart(fig_rider_map, use_container_width=True)

        st.markdown("##### ⏱️ 各时段超时率")
        to_arr = snap.get("timeout_rate_array", [])
        if to_arr:
            to_df = pd.DataFrame(to_arr)
            if not to_df.empty:
                fig_to = go.Figure()
                fig_to.add_trace(go.Bar(
                    x=to_df["time_slot"], y=to_df["timeout_rate_pct"],
                    name="超时率(%)", marker_color="#e74c3c"
                ))
                fig_to.add_hline(y=8, line_dash="dash", line_color="red",
                                     annotation_text="阈值8%")
                fig_to.update_layout(title="各时段超时率")
                st.plotly_chart(fig_to, use_container_width=True)

        st.markdown("##### 🌦️ 天气数据")
        wd = snap.get("weather_data_summary", {})
        if wd:
            wc1, wc2, wc3, wc4 = st.columns(4)
            with wc1:
                st.metric("天气", wd.get("current_weather", ""))
            with wc2:
                st.metric("影响系数", f"x{wd.get('impact_factor', 1)}")
            with wc3:
                st.metric("影响等级", wd.get("impact_level", ""))
            with wc4:
                st.metric("是否恶劣", "是" if wd.get("is_severe") else "否")
    else:
        st.info("无快照数据")


with tab_playback:
    st.subheader("🎬 预警详情回放与对比模式")
    st.caption("选择预警记录查看完整上下文快照，支持预警时刻与解除后30分钟并列对比")

    all_records = get_peak_warnings()
    if not all_records:
        st.info("暂无预警记录可供回放")
    else:
        record_options = []
        for r in all_records:
            ctx_r = r.get("business_context", {})
            label = f"[{r.get('warning_level','')}] {ctx_r.get('district','')} | {r.get('timestamp','')[:19]} | {r.get('scenario_tag','普通')}"
            record_options.append((r["record_id"], label))

        selected_id = st.selectbox(
            "选择要回放的预警记录",
            [rid for rid, _ in record_options],
            format_func=lambda rid: next((lab for rrid, lab in record_options if rrid == rid), ""),
            key="pb_select"
        )

        selected_record = get_peak_warning_by_id(selected_id)
        if selected_record:
            warn_snap = selected_record.get("warning_snapshot", {})
            post_snap = selected_record.get("post_resolution_snapshot")
            ctx_r = selected_record.get("business_context", {})

            comp_mode = st.toggle("🔀 开启对比模式（预警时刻 vs 解除后30分钟）",
                                      value=bool(post_snap), disabled=not post_snap)

            if comp_mode and post_snap:
                st.info(f"🔀 对比模式：左=预警时刻 | 右=解除后30分钟")
                col_l, col_r_pane = st.columns(2)

                with col_l:
                    st.markdown("#### 🔴 预警时刻快照")
                    _render_snapshot_panel(warn_snap, "warning")

                with col_r_pane:
                    st.markdown("#### 🟢 解除后30分钟快照")
                    _render_snapshot_panel(post_snap, "resolved")

            else:
                _render_snapshot_panel(warn_snap, "warning")

            st.markdown("---")
            with st.expander("🔍 阈值命中详情", expanded=True):
                hits = selected_record.get("threshold_hits", [])
                if hits:
                    hits_df = pd.DataFrame([{
                        "维度": h["dimension"],
                        "当前值": h["value"],
                        "预警阈值": h["warning_threshold"],
                        "严重阈值": h["critical_threshold"],
                        "命中等级": h["hit_level"],
                        "动态阈值": "是" if h["is_dynamic"] else "否",
                        "时段系数": h["time_slot_adjust"],
                        "超标倍数": h["exceed_ratio"]
                    } for h in hits])
                    st.dataframe(hits_df, use_container_width=True, hide_index=True)
                else:
                    st.info("无阈值命中")

            st.markdown("---")
            with st.expander("📦 完整原始快照JSON数据", expanded=False):
                st.json({k: v for k, v in selected_record.items()
                           if k not in ["warning_snapshot", "post_resolution_snapshot"]})
                st.markdown("#### 预警时刻快照模块状态：")
                st.json({k: v for k, v in warn_snap.items() if k != "hotspot_image_base64"})
                if post_snap:
                    st.markdown("#### 解除后快照模块状态：")
                    st.json({k: v for k, v in post_snap.items() if k != "hotspot_image_base64"})

with tab_operation:
    st.subheader("📝 补贴策略与峰值预警记录")

    col_op1, col_op2 = st.columns([1, 1])

    with col_op1:
        st.markdown("#### 🎯 当前补贴策略建议")
        st.info(f"预警级别：**{subsidy_info['预警级别']}**  |  供需比：{warning_info['供需比']}单/骑手  |  责任人：**{get_district_responsible(ctx['district'])}**")

        subsidy_df = pd.DataFrame(subsidy_info["补贴策略"])
        st.dataframe(subsidy_df, use_container_width=True, hide_index=True)

        if st.button("✅ 执行补贴策略并写入操作日志", type="primary", use_container_width=True):
            log_entry = log_subsidy_operation(operator, subsidy_info, ctx)
            st.success(f"✅ 已写入操作日志，日志ID：{log_entry['log_id']}")

    with col_op2:
        st.markdown("#### ⚠️ 当前峰值预警（增强版四维监测）")
        level_badge = {"严重": "🔴 严重", "警告": "🟡 警告", "正常": "🟢 正常"}
        st.info(f"预警级别：**{level_badge.get(warning_enhanced['预警级别'], warning_enhanced['预警级别'])}**  |  责任人：**{get_district_responsible(ctx['district'])}**")

        for w in warning_enhanced["预警内容"]:
            st.write(f"• {w}")

        if st.button("📝 记录峰值预警到最终记录", type="primary", use_container_width=True):
            record = record_peak_warning(warning_info, ctx)
            st.success(f"✅ 已记录峰值预警，记录ID：{record['record_id']}")

    st.markdown("---")
    col_log1, col_log2 = st.columns([1, 1])
    with col_log1:
        st.markdown("#### 📋 操作日志（补贴策略）")
        op_logs = get_operation_logs()
        op_df = logs_to_dataframe(op_logs)
        if not op_df.empty:
            st.dataframe(op_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无操作日志")

    with col_log2:
        st.markdown("#### 📜 峰值预警记录")
        pk_records = get_peak_warnings()
        pk_df = warnings_to_dataframe(pk_records)
        if not pk_df.empty:
            display_cols = ["时间", "预警级别", "商圈", "时段", "触发维度", "可回放", "场景标签"]
            st.dataframe(pk_df[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("暂无峰值预警记录")

