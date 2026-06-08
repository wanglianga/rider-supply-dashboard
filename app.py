import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, date

from data_generator import (
    BUSINESS_DISTRICTS, WEATHER_TYPES, TIME_SLOTS,
    generate_business_context, generate_hotspot_data,
    generate_rider_data, generate_timeout_data,
    generate_weather_data, detect_peak_warning,
    generate_subsidy_suggestion
)
from log_manager import (
    log_subsidy_operation, record_peak_warning,
    save_acceptance_snapshot, get_operation_logs,
    get_peak_warnings, get_acceptance_snapshots,
    logs_to_dataframe, warnings_to_dataframe, snapshots_to_dataframe
)

st.set_page_config(
    page_title="外卖商圈骑手供需分析看板",
    page_icon="🛵",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🛵 外卖商圈骑手供需分析看板")
st.markdown("---")

with st.sidebar:
    st.header("📋 业务上下文设置")
    st.caption("所有模块共享同一上下文，参数变更会联动更新全部数据")

    selected_date = st.date_input("选择日期", value=date.today())
    district = st.selectbox("选择商圈", BUSINESS_DISTRICTS, index=1)
    weather = st.selectbox("天气状况", WEATHER_TYPES, index=2)
    time_slot = st.selectbox("分析时段", TIME_SLOTS, index=2)

    st.markdown("---")
    operator = st.text_input("操作人", value="调度员A")

    refresh_btn = st.button("🔄 刷新数据（基于当前上下文）", use_container_width=True, type="primary")

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
    st.session_state.subsidy = generate_subsidy_suggestion(context, st.session_state.warning)
else:
    context = st.session_state.context

ctx = st.session_state.context
hotspot_df = st.session_state.hotspot
rider_data = st.session_state.rider
timeout_data = st.session_state.timeout
weather_data = st.session_state.weather_data
warning_info = st.session_state.warning
subsidy_info = st.session_state.subsidy

st.markdown("### 📍 当前业务上下文")
col_ctx1, col_ctx2, col_ctx3, col_ctx4, col_ctx5 = st.columns(5)
with col_ctx1:
    st.metric("商圈", ctx["district"])
with col_ctx2:
    st.metric("时段", f'{ctx["time_slot"]} {"⭐高峰期" if ctx["is_peak"] else ""}')
with col_ctx3:
    st.metric("天气", f'{ctx["weather"]} (系数x{ctx["weather_factor"]})')
with col_ctx4:
    level_color = {"严重": "🔴", "警告": "🟡", "正常": "🟢"}
    st.metric("预警级别", f'{level_color.get(warning_info["预警级别"], "")} {warning_info["预警级别"]}')
with col_ctx5:
    st.metric("供需比", f'{warning_info["供需比"]} 单/骑手')

st.markdown("---")

tab_hotspot, tab_rider, tab_timeout, tab_weather, tab_operation, tab_playback = st.tabs([
    "🔥 订单热区", "👥 骑手在线", "⏱️ 超时率", "🌦️ 天气影响", "📝 操作与记录", "🎬 验收与回放"
])

with tab_hotspot:
    st.subheader("订单热区分布")
    st.caption("基于当前业务上下文实时计算")

    col_h1, col_h2 = st.columns([1, 1])
    with col_h1:
        fig_hotspot = px.bar(
            hotspot_df, x="子区域", y="订单量",
            color="热区等级",
            color_discrete_map={"低负荷": "#2ecc71", "正常": "#f1c40f", "高热区": "#e74c3c"},
            title="各子区域订单量与热区等级",
            text="订单量"
        )
        st.plotly_chart(fig_hotspot, use_container_width=True)

    with col_h2:
        fig_supply = px.scatter(
            hotspot_df, x="供需比", y="订单量", size="商户密度",
            color="热区等级", hover_data=["子区域", "预计送达时长(分钟)"],
            color_discrete_map={"低负荷": "#2ecc71", "正常": "#f1c40f", "高热区": "#e74c3c"},
            title="供需比 vs 订单量（气泡大小=商户密度）"
        )
        st.plotly_chart(fig_supply, use_container_width=True)

    st.dataframe(hotspot_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    col_save_hs, col_snap_hs = st.columns(2)
    with col_save_hs:
        if st.button("💾 保存此热区分析为验收快照", key="save_hs_snap"):
            snap = save_acceptance_snapshot(
                "订单热区输入",
                {
                    "context": ctx,
                    "hotspot_data": hotspot_df.to_dict(orient="records"),
                    "warning_summary": warning_info
                },
                f"{ctx['district']}-{ctx['time_slot']} 热区分析"
            )
            st.success(f"✅ 已保存热区快照：{snap['snapshot_id']}")

with tab_rider:
    st.subheader("骑手在线状态")
    st.caption("与订单热区共享同一上下文")

    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        st.metric("总注册骑手", rider_data["总注册骑手"])
    with col_r2:
        st.metric("在线骑手", rider_data["在线骑手"])
    with col_r3:
        st.metric("配送中骑手", rider_data["配送中骑手"])
    with col_r4:
        st.metric("人均配送单量", f"{rider_data['人均配送单量']}单")

    col_r5, col_r6 = st.columns([1, 1])
    with col_r5:
        fig_rider_pie = px.pie(
            rider_data["骑手状态分布"],
            names="状态", values="人数",
            title="骑手状态分布",
            color_discrete_sequence=["#e74c3c", "#3498db", "#95a5a6"]
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
        fig_rider_trend.update_layout(title="近期骑手在线趋势")
        st.plotly_chart(fig_rider_trend, use_container_width=True)

    st.dataframe(rider_data["骑手状态分布"], use_container_width=True, hide_index=True)

with tab_timeout:
    st.subheader("超时率分析")
    st.caption("超时判定阈值：8%，与热区、骑手、天气数据联动")

    col_t1, col_t2, col_t3, col_t4 = st.columns(4)
    with col_t1:
        st.metric("总订单数", timeout_data["总订单数"])
    with col_t2:
        st.metric("超时订单数", timeout_data["超时订单数"])
    with col_t3:
        rate_val = round(timeout_data["超时率"] * 100, 2)
        delta = f"{round(rate_val - 8, 2)}% vs 阈值"
        st.metric("超时率", f"{rate_val}%", delta=delta, delta_color="inverse")
    with col_t4:
        status = "🔴 超标" if timeout_data["是否超标"] else "🟢 正常"
        st.metric("判定结果", status)

    col_t5, col_t6 = st.columns([1, 1])
    with col_t5:
        fig_timeout_reason = px.bar(
            timeout_data["超时原因分布"], x="原因", y="订单数",
            color="占比", title="超时原因分布", text="订单数"
        )
        st.plotly_chart(fig_timeout_reason, use_container_width=True)

    with col_t6:
        fig_timeout_trend = px.line(
            timeout_data["近7日趋势"], x="日期", y="超时率",
            title="近7日超时率趋势", markers=True
        )
        fig_timeout_trend.add_hline(y=0.08, line_dash="dash", line_color="red",
                                    annotation_text="阈值 8%")
        fig_timeout_trend.update_layout(yaxis_tickformat=".1%")
        st.plotly_chart(fig_timeout_trend, use_container_width=True)

    st.dataframe(timeout_data["超时原因分布"], use_container_width=True, hide_index=True)

    st.markdown("---")
    if st.button("📌 保存此超时率判定为验收快照", key="save_to_snap"):
        snap = save_acceptance_snapshot(
            "超时率判定",
            {
                "context": ctx,
                "timeout_data": {k: v.to_dict(orient="records") if isinstance(v, pd.DataFrame) else v
                                 for k, v in timeout_data.items()},
                "判定结果": "超标" if timeout_data["是否超标"] else "正常"
            },
            f"{ctx['district']} 超时率{round(timeout_data['超时率'] * 100, 2)}%"
        )
        st.success(f"✅ 已保存超时率判定快照：{snap['snapshot_id']}")

with tab_weather:
    st.subheader("天气影响分析")
    st.caption("天气系数直接影响订单量预估、配送时长和超时率，与其他模块共享上下文")

    impact = weather_data["影响摘要"]
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        st.metric("当前天气", impact["当前天气"])
    with col_w2:
        st.metric("影响系数", f'x{impact["影响系数"]}')
    with col_w3:
        st.metric("订单增量预估", impact["订单增量预估"])

    col_w4, col_w5 = st.columns(2)
    with col_w4:
        st.metric("配送时长增加", impact["配送时长增加"])
    with col_w5:
        st.metric("补贴建议", impact["补贴建议"])

    st.markdown("#### 各类天气影响对比")
    st.dataframe(weather_data["天气对比表"], use_container_width=True, hide_index=True)

    st.markdown("#### 分时段天气影响")
    fig_weather = px.bar(
        weather_data["分时段影响"], x="时段", y=["天气影响订单量", "天气影响超时率"],
        barmode="group", title="分时段天气影响趋势"
    )
    st.plotly_chart(fig_weather, use_container_width=True)

with tab_operation:
    st.subheader("补贴策略与峰值预警记录")

    col_op1, col_op2 = st.columns([1, 1])

    with col_op1:
        st.markdown("#### 🎯 当前补贴策略建议")
        st.info(f"预警级别：**{subsidy_info['预警级别']}**  |  供需比：{warning_info['供需比']}单/骑手")

        subsidy_df = pd.DataFrame(subsidy_info["补贴策略"])
        st.dataframe(subsidy_df, use_container_width=True, hide_index=True)

        if st.button("✅ 执行补贴策略并写入操作日志", type="primary", use_container_width=True):
            log_entry = log_subsidy_operation(operator, subsidy_info, ctx)
            st.success(f"✅ 已写入操作日志，日志ID：{log_entry['log_id']}")

    with col_op2:
        st.markdown("#### ⚠️ 当前峰值预警")
        level_badge = {"严重": "🔴 严重", "警告": "🟡 警告", "正常": "🟢 正常"}
        st.info(f"预警级别：**{level_badge.get(warning_info['预警级别'], warning_info['预警级别'])}**")

        for w in warning_info["预警内容"]:
            st.write(f"• {w}")

        if st.button("📝 记录峰值预警到最终记录", type="primary", use_container_width=True):
            record = record_peak_warning(warning_info, ctx)
            st.success(f"✅ 已记录峰值预警，记录ID：{record['record_id']}")

        if st.button("📸 保存峰值预警回看快照", use_container_width=True):
            snap = save_acceptance_snapshot(
                "峰值预警回看",
                {
                    "context": ctx,
                    "warning_info": warning_info,
                    "subsidy_info": subsidy_info
                },
                f"{warning_info['预警级别']}预警-{ctx['district']}"
            )
            st.success(f"✅ 已保存峰值预警快照：{snap['snapshot_id']}")

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
        st.markdown("#### 📜 峰值预警记录（最终记录）")
        pk_records = get_peak_warnings()
        pk_df = warnings_to_dataframe(pk_records)
        if not pk_df.empty:
            st.dataframe(pk_df, use_container_width=True, hide_index=True)
        else:
            st.info("暂无峰值预警记录")

with tab_playback:
    st.subheader("🎬 验收说明与历史回放")
    st.caption("保留订单热区输入、超时率判定和峰值预警回看的验收快照")

    snap_type = st.radio(
        "选择验收快照类型",
        ["全部", "订单热区输入", "超时率判定", "峰值预警回看"],
        horizontal=True
    )
    filter_type = None if snap_type == "全部" else snap_type
    snapshots = get_acceptance_snapshots(snapshot_type=filter_type)
    snap_df = snapshots_to_dataframe(snapshots)

    if not snap_df.empty:
        st.dataframe(snap_df, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("#### 🎞️ 选择快照回放详细内容")
        selected_idx = st.selectbox(
            "选择要回放的快照",
            range(len(snapshots)),
            format_func=lambda i: f"{snapshots[i]['snapshot_type']} | {snapshots[i]['timestamp']} | {snapshots[i]['description']}"
        )
        if selected_idx is not None:
            selected = snapshots[selected_idx]
            st.markdown(f"**快照ID**：{selected['snapshot_id']}")
            st.markdown(f"**类型**：{selected['snapshot_type']}")
            st.markdown(f"**时间**：{selected['timestamp']}")
            st.markdown(f"**描述**：{selected['description']}")

            with st.expander("🔍 查看完整快照数据", expanded=True):
                st.json(selected["data"])
    else:
        st.info("暂无验收快照，请在各模块中点击保存快照按钮生成")

    st.markdown("---")
    st.markdown("### 📑 验收说明清单")
    checklist_items = [
        ("订单热区输入", get_acceptance_snapshots(snapshot_type="订单热区输入")),
        ("超时率判定", get_acceptance_snapshots(snapshot_type="超时率判定")),
        ("峰值预警回看", get_acceptance_snapshots(snapshot_type="峰值预警回看"))
    ]
    for name, items in checklist_items:
        status = "✅ 已保存" if items else "❌ 未保存"
        st.markdown(f"- **{name}**：{status}（共 {len(items)} 条记录）")
