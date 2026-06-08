import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import hashlib
import base64
import io
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib
from data_generator import (
    BUSINESS_DISTRICTS, WEATHER_TYPES, TIME_SLOTS, PEAK_SLOTS,
    WEATHER_IMPACT_FACTOR, DATA_SCHEMA_VERSION, DISTRICT_RESPONSIBLE,
    generate_business_context, generate_hotspot_data, generate_rider_data,
    generate_timeout_data, generate_weather_data, get_district_responsible
)

WARNING_DIMENSIONS = ["供需比", "超时率", "骑手负载均衡度", "天气恶劣指数"]
WARNING_LEVELS = ["正常", "警告", "严重"]

DEFAULT_THRESHOLDS = {
    "供需比": {
        "warning": 8.0,
        "critical": 12.0,
        "dynamic": True,
        "time_slot_adjust": {
            "06:00-09:00": 0.8,
            "09:00-11:00": 0.9,
            "11:00-13:00": 1.3,
            "13:00-17:00": 0.9,
            "17:00-20:00": 1.4,
            "20:00-23:00": 1.0
        }
    },
    "超时率": {
        "warning": 0.06,
        "critical": 0.10,
        "dynamic": True,
        "time_slot_adjust": {
            "06:00-09:00": 1.0,
            "09:00-11:00": 1.0,
            "11:00-13:00": 1.2,
            "13:00-17:00": 1.0,
            "17:00-20:00": 1.2,
            "20:00-23:00": 1.1
        }
    },
    "骑手负载均衡度": {
        "warning": 5,
        "critical": 8,
        "dynamic": False,
        "time_slot_adjust": {}
    },
    "天气恶劣指数": {
        "warning": 1.3,
        "critical": 1.7,
        "dynamic": False,
        "time_slot_adjust": {}
    }
}


def get_effective_thresholds(context, custom_thresholds=None):
    base = custom_thresholds if custom_thresholds else DEFAULT_THRESHOLDS
    time_slot = context.get("time_slot", TIME_SLOTS[2])
    effective = {}
    for dim, cfg in base.items():
        adjust = 1.0
        if cfg.get("dynamic") and cfg.get("time_slot_adjust"):
            adjust = cfg["time_slot_adjust"].get(time_slot, 1.0)
        effective[dim] = {
            "warning": round(cfg["warning"] * adjust, 4),
            "critical": round(cfg["critical"] * adjust, 4),
            "base_warning": cfg["warning"],
            "base_critical": cfg["critical"],
            "dynamic": cfg.get("dynamic", False),
            "time_slot_adjust": adjust
        }
    return effective


def calculate_dimension_values(context, hotspot_wrapper, rider_data, timeout_data, weather_data):
    hotspot_df = hotspot_wrapper["data"]
    total_orders = timeout_data["总订单数"]
    online_riders = rider_data["在线骑手"]
    supply_demand_ratio = round(total_orders / max(online_riders, 1), 2)
    timeout_rate = timeout_data["超时率"]

    rider_order_counts = []
    for i in range(online_riders):
        base_orders = rider_data["人均配送单量"]
        variance = random.uniform(-2, 4)
        rider_order_counts.append(max(1, round(base_orders + variance)))
    if len(rider_order_counts) >= 2:
        load_balance_diff = max(rider_order_counts) - min(rider_order_counts)
    else:
        load_balance_diff = 0
    load_balance_diff = int(load_balance_diff)

    weather_severity = context.get("weather_factor", 1.0)

    return {
        "供需比": supply_demand_ratio,
        "超时率": round(timeout_rate, 4),
        "骑手负载均衡度": load_balance_diff,
        "天气恶劣指数": round(weather_severity, 2),
        "_rider_order_counts": rider_order_counts
    }


def evaluate_threshold_hits(dim_values, effective_thresholds):
    hits = []
    overall_level = "正常"

    for dim in WARNING_DIMENSIONS:
        value = dim_values.get(dim)
        th = effective_thresholds.get(dim, {})
        if value is None:
            continue

        level = "正常"
        if value >= th.get("critical", float("inf")):
            level = "严重"
        elif value >= th.get("warning", float("inf")):
            level = "警告"

        if level != "正常":
            if level == "严重":
                overall_level = "严重"
            elif level == "警告" and overall_level != "严重":
                overall_level = "警告"

        hits.append({
            "dimension": dim,
            "value": value,
            "warning_threshold": th.get("warning"),
            "critical_threshold": th.get("critical"),
            "is_dynamic": th.get("dynamic", False),
            "time_slot_adjust": th.get("time_slot_adjust", 1.0),
            "hit_level": level,
            "exceed_ratio": round(value / th.get("warning", 1), 3) if level != "正常" else 0
        })

    return hits, overall_level


def generate_rider_distribution_points(context, rider_data, hotspot_wrapper):
    hotspot_df = hotspot_wrapper["data"]
    district = context["district"]
    online_riders = rider_data["在线骑手"]

    points = []
    sub_areas = hotspot_df["子区域"].tolist()
    area_orders = hotspot_df["订单量"].tolist()
    total_orders = sum(area_orders) if sum(area_orders) > 0 else 1

    rider_idx = 0
    for area_idx, area in enumerate(sub_areas):
        area_ratio = area_orders[area_idx] / total_orders
        riders_in_area = max(1, int(online_riders * area_ratio))
        for _ in range(riders_in_area):
            if rider_idx >= online_riders:
                break
            points.append({
                "rider_id": f"R-{district[:2]}-{rider_idx + 1:03d}",
                "sub_area": area,
                "x": round(10 + area_idx * 14 + random.uniform(-3, 3), 2),
                "y": round(10 + random.uniform(0, 80), 2),
                "status": random.choice(["配送中", "空闲", "取餐中"]),
                "current_orders": random.randint(1, 6),
                "lon": round(116.3 + area_idx * 0.02 + random.uniform(-0.005, 0.005), 5),
                "lat": round(39.9 + random.uniform(-0.02, 0.02), 5)
            })
            rider_idx += 1

    while rider_idx < online_riders:
        points.append({
            "rider_id": f"R-{district[:2]}-{rider_idx + 1:03d}",
            "sub_area": random.choice(sub_areas),
            "x": round(random.uniform(5, 95), 2),
            "y": round(random.uniform(5, 95), 2),
            "status": random.choice(["配送中", "空闲", "取餐中"]),
            "current_orders": random.randint(1, 6),
            "lon": round(116.3 + random.uniform(-0.05, 0.05), 5),
            "lat": round(39.9 + random.uniform(-0.05, 0.05), 5)
        })
        rider_idx += 1

    return points


def generate_timeout_rate_array(context):
    rates = []
    base_rate = 0.04
    weather_factor = context.get("weather_factor", 1.0)
    is_peak = context.get("is_peak", False)

    for slot in TIME_SLOTS:
        slot_peak = slot in PEAK_SLOTS
        slot_factor = 1.5 if slot_peak else 1.0
        variance = random.uniform(-0.01, 0.02)
        rate = round(base_rate * weather_factor * slot_factor + variance, 4)
        rate = max(0.01, min(0.30, rate))
        rates.append({
            "time_slot": slot,
            "timeout_rate": rate,
            "timeout_rate_pct": round(rate * 100, 2),
            "is_peak": slot_peak
        })
    return rates


def generate_hotspot_image_base64(context, hotspot_wrapper):
    hotspot_df = hotspot_wrapper["data"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    colors_map = {"低负荷": "#2ecc71", "正常": "#f1c40f", "高热区": "#e74c3c"}
    bar_colors = [colors_map.get(lv, "#95a5a6") for lv in hotspot_df["热区等级"]]

    axes[0].bar(hotspot_df["子区域"], hotspot_df["订单量"], color=bar_colors)
    axes[0].set_title(f"{context['district']} - {context['time_slot']} 订单热区分布")
    axes[0].set_xlabel("子区域")
    axes[0].set_ylabel("订单量")
    axes[0].tick_params(axis="x", rotation=45)
    for i, v in enumerate(hotspot_df["订单量"]):
        axes[0].text(i, v, str(v), ha="center", va="bottom", fontsize=8)

    scatter = axes[1].scatter(
        hotspot_df["供需比"], hotspot_df["订单量"],
        s=hotspot_df["商户密度"] * 300,
        c=bar_colors, alpha=0.7, edgecolors="white"
    )
    axes[1].set_title("供需比 vs 订单量")
    axes[1].set_xlabel("供需比 (单/骑手)")
    axes[1].set_ylabel("订单量")
    axes[1].axvline(x=8.0, color="orange", linestyle="--", alpha=0.5, label="预警阈值")
    axes[1].axvline(x=12.0, color="red", linestyle="--", alpha=0.5, label="严重阈值")
    axes[1].legend(fontsize=7)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=80, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode("utf-8")
    return img_b64


def generate_full_snapshot(context, hotspot_wrapper, rider_data, timeout_data, weather_data):
    dim_values = calculate_dimension_values(context, hotspot_wrapper, rider_data, timeout_data, weather_data)
    effective_thresholds = get_effective_thresholds(context)
    threshold_hits, overall_level = evaluate_threshold_hits(dim_values, effective_thresholds)

    hotspot_image_b64 = generate_hotspot_image_base64(context, hotspot_wrapper)
    rider_points = generate_rider_distribution_points(context, rider_data, hotspot_wrapper)
    timeout_array = generate_timeout_rate_array(context)

    hotspot_df = hotspot_wrapper["data"]

    snapshot = {
        "snapshot_id": f"snap-{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": datetime.now().isoformat(),
        "business_context": {
            "district": context["district"],
            "time_slot": context["time_slot"],
            "weather": context["weather"],
            "is_peak": context["is_peak"],
            "weather_factor": context["weather_factor"],
            "selected_date": str(context.get("selected_date", datetime.now().date())),
            "responsible": get_district_responsible(context["district"])
        },
        "dimension_values": {k: v for k, v in dim_values.items() if not k.startswith("_")},
        "effective_thresholds": effective_thresholds,
        "threshold_hits": threshold_hits,
        "overall_warning_level": overall_level,
        "hotspot_image_base64": hotspot_image_b64,
        "rider_distribution_points": rider_points,
        "timeout_rate_array": timeout_array,
        "weather_data_summary": {
            "current_weather": weather_data["影响摘要"]["当前天气"],
            "impact_factor": weather_data["影响摘要"]["影响系数"],
            "impact_level": weather_data["影响摘要"]["影响等级"],
            "is_severe": weather_data["影响摘要"]["是否恶劣天气"],
            "order_increase": weather_data["影响摘要"]["订单增量预估"],
            "delivery_increase": weather_data["影响摘要"]["配送时长增加"]
        },
        "modules_state": {
            "hotspot": {
                "summary": hotspot_wrapper["summary"],
                "data_records": hotspot_df.to_dict(orient="records")
            },
            "rider": {
                "total_registered": rider_data["总注册骑手"],
                "online": rider_data["在线骑手"],
                "delivering": rider_data["配送中骑手"],
                "idle": rider_data["空闲骑手"],
                "avg_orders_per_rider": rider_data["人均配送单量"],
                "online_rate_pct": rider_data["在线率(%)"],
                "anomaly_detected": rider_data.get("异常检测", {}).get("是否异常", False),
                "anomaly_count": rider_data.get("异常检测", {}).get("异常数量", 0),
                "rider_order_counts": dim_values.get("_rider_order_counts", [])
            },
            "timeout": {
                "total_orders": timeout_data["总订单数"],
                "timeout_orders": timeout_data["超时订单数"],
                "timeout_rate": timeout_data["超时率"],
                "timeout_rate_pct": timeout_data["超时率(%)"],
                "is_over_threshold": timeout_data["是否超标"],
                "reasons": timeout_data["超时原因分布"].to_dict(orient="records") if isinstance(timeout_data["超时原因分布"], pd.DataFrame) else timeout_data["超时原因分布"]
            },
            "weather": {
                "impact_summary": weather_data["影响摘要"],
                "hourly_impact": weather_data["分时段影响"].to_dict(orient="records") if isinstance(weather_data["分时段影响"], pd.DataFrame) else weather_data["分时段影响"]
            }
        }
    }
    return snapshot


def simulate_post_resolution_state(context, hotspot_wrapper, rider_data, timeout_data, weather_data, minutes=30):
    resolved_context = context.copy()
    prev_weather = context.get("weather_factor", 1.0)
    resolved_context["weather_factor"] = round(max(1.0, prev_weather * 0.7), 2)
    resolved_context["timestamp"] = (datetime.now() + timedelta(minutes=minutes)).isoformat()

    resolved_hotspot_df = hotspot_wrapper["data"].copy()
    resolved_hotspot_df["订单量"] = (resolved_hotspot_df["订单量"] * 0.65).astype(int)
    resolved_hotspot_df["供需比"] = (resolved_hotspot_df["供需比"] * 0.6).round(2)
    resolved_hotspot_df["热区等级"] = resolved_hotspot_df["供需比"].apply(
        lambda x: "高热区" if x > 3.0 else ("正常" if x > 1.5 else "低负荷")
    )
    resolved_hotspot_wrapper = {
        "data": resolved_hotspot_df,
        "version_trace": hotspot_wrapper.get("version_trace", {}),
        "summary": {
            "总子区域数": len(resolved_hotspot_df),
            "高热区数量": int((resolved_hotspot_df["热区等级"] == "高热区").sum()),
            "正常区域数": int((resolved_hotspot_df["热区等级"] == "正常").sum()),
            "低负荷区域数": int((resolved_hotspot_df["热区等级"] == "低负荷").sum()),
            "总订单量": int(resolved_hotspot_df["订单量"].sum()),
            "平均供需比": round(float(resolved_hotspot_df["供需比"].mean()), 2)
        }
    }

    resolved_rider = rider_data.copy()
    resolved_rider["在线骑手"] = int(rider_data["在线骑手"] * 1.25)
    resolved_rider["空闲骑手"] = max(5, int(rider_data["空闲骑手"] * 2.5))
    resolved_rider["配送中骑手"] = resolved_rider["在线骑手"] - resolved_rider["空闲骑手"]
    resolved_rider["人均配送单量"] = round(rider_data["人均配送单量"] * 0.6, 1)

    resolved_timeout = timeout_data.copy()
    resolved_timeout["超时率"] = round(timeout_data["超时率"] * 0.55, 4)
    resolved_timeout["超时率(%)"] = round(resolved_timeout["超时率"] * 100, 2)
    resolved_timeout["超时订单数"] = int(timeout_data["超时订单数"] * 0.5)
    resolved_timeout["是否超标"] = resolved_timeout["超时率"] > 0.08
    resolved_timeout["判定结果"] = "超标" if resolved_timeout["是否超标"] else "正常"

    resolved_weather = weather_data.copy()
    resolved_weather["影响摘要"] = weather_data["影响摘要"].copy()
    resolved_weather["影响摘要"]["影响系数"] = resolved_context["weather_factor"]
    resolved_weather["影响摘要"]["影响等级"] = (
        "轻微" if resolved_context["weather_factor"] <= 1.1
        else "中等" if resolved_context["weather_factor"] <= 1.5
        else "严重"
    )
    resolved_weather["影响摘要"]["是否恶劣天气"] = resolved_context["weather_factor"] > 1.2

    return resolved_context, resolved_hotspot_wrapper, resolved_rider, resolved_timeout, resolved_weather


def detect_peak_warning_enhanced(context, hotspot_wrapper, rider_data, timeout_data, weather_data, custom_thresholds=None):
    dim_values = calculate_dimension_values(context, hotspot_wrapper, rider_data, timeout_data, weather_data)
    effective_thresholds = get_effective_thresholds(context, custom_thresholds)
    threshold_hits, overall_level = evaluate_threshold_hits(dim_values, effective_thresholds)

    warning_messages = []
    for hit in threshold_hits:
        if hit["hit_level"] != "正常":
            dim = hit["dimension"]
            val = hit["value"]
            th_w = hit["warning_threshold"]
            th_c = hit["critical_threshold"]
            dynamic_note = " (动态阈值)" if hit["is_dynamic"] else ""
            if dim == "超时率":
                val_str = f"{round(val * 100, 2)}%"
                th_w_str = f"{round(th_w * 100, 2)}%"
                th_c_str = f"{round(th_c * 100, 2)}%"
            else:
                val_str = str(val)
                th_w_str = str(th_w)
                th_c_str = str(th_c)
            warning_messages.append(
                f"{dim}{dynamic_note}: {val_str} "
                f"(预警阈值: {th_w_str}, 严重阈值: {th_c_str}) "
                f"→ {hit['hit_level']}"
            )

    if not warning_messages:
        warning_messages = ["所有维度正常，无预警触发"]

    return {
        "预警级别": overall_level,
        "预警内容": warning_messages,
        "供需比": dim_values["供需比"],
        "检测时间": datetime.now().isoformat(),
        "维度检测详情": {
            dim: {
                "当前值": dim_values.get(dim),
                "预警阈值": effective_thresholds[dim]["warning"],
                "严重阈值": effective_thresholds[dim]["critical"],
                "是否动态阈值": effective_thresholds[dim]["dynamic"],
                "时段调整系数": effective_thresholds[dim]["time_slot_adjust"]
            }
            for dim in WARNING_DIMENSIONS
        },
        "阈值命中详情": threshold_hits,
        "上下文摘要": {
            "商圈": context["district"],
            "时段": context["time_slot"],
            "天气": context["weather"],
            "是否高峰期": context["is_peak"],
            "当前责任人": get_district_responsible(context["district"])
        },
        "骑手异常摘要": rider_data.get("异常检测", {})
    }


def create_acceptance_scenario(scenario_type):
    if scenario_type == "供需比预警":
        ctx = generate_business_context(
            district="国贸商圈",
            weather="晴",
            time_slot="11:00-13:00"
        )
        ctx["weather_factor"] = 1.0
        ctx["peak_multiplier"] = 2.8
        ctx["base_orders"] = 2500
        ctx["base_riders"] = 70
    elif scenario_type == "超时率预警":
        ctx = generate_business_context(
            district="中关村商圈",
            weather="小雨",
            time_slot="17:00-20:00"
        )
        ctx["weather_factor"] = 1.4
        ctx["peak_multiplier"] = 1.8
        ctx["base_orders"] = 1000
        ctx["base_riders"] = 55
    elif scenario_type == "多维度复合预警":
        ctx = generate_business_context(
            district="三里屯商圈",
            weather="大雨",
            time_slot="17:00-20:00"
        )
        ctx["weather_factor"] = 2.0
        ctx["peak_multiplier"] = 2.2
        ctx["base_orders"] = 1800
        ctx["base_riders"] = 55
    else:
        ctx = generate_business_context()

    hotspot = generate_hotspot_data(ctx)
    rider = generate_rider_data(ctx)
    timeout = generate_timeout_data(ctx)
    weather = generate_weather_data(ctx)

    return ctx, hotspot, rider, timeout, weather
