import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import hashlib

BUSINESS_DISTRICTS = [
    "中关村商圈", "国贸商圈", "望京商圈", "三里屯商圈",
    "西单商圈", "朝阳大悦城商圈", "五道口商圈", "亦庄商圈"
]

WEATHER_TYPES = ["晴", "多云", "小雨", "中雨", "大雨", "雪", "雾霾"]

WEATHER_IMPACT_FACTOR = {
    "晴": 1.0,
    "多云": 1.05,
    "小雨": 1.3,
    "中雨": 1.6,
    "大雨": 2.0,
    "雪": 1.8,
    "雾霾": 1.2
}

TIME_SLOTS = [
    "06:00-09:00", "09:00-11:00", "11:00-13:00",
    "13:00-17:00", "17:00-20:00", "20:00-23:00"
]

PEAK_SLOTS = ["11:00-13:00", "17:00-20:00"]

DATA_SCHEMA_VERSION = "2.1.0"

DISTRICT_RESPONSIBLE = {
    "中关村商圈": "张伟-调度组长",
    "国贸商圈": "李娜-高级调度",
    "望京商圈": "王强-调度员",
    "三里屯商圈": "刘芳-调度员",
    "西单商圈": "陈明-高级调度",
    "朝阳大悦城商圈": "赵丽-调度组长",
    "五道口商圈": "孙浩-调度员",
    "亦庄商圈": "周敏-调度员"
}

RIDER_ANOMALY_THRESHOLDS = {
    "min_online_ratio": 0.5,
    "min_idle_riders": 3,
    "max_delivery_ratio": 0.92,
    "max_drop_rate": 0.15
}


def _generate_version_signature(context, data_type):
    raw = f"{DATA_SCHEMA_VERSION}|{data_type}|{context.get('district')}|{context.get('time_slot')}|{context.get('weather')}|{context.get('selected_date')}|{context.get('timestamp')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _build_version_trace(context, data_type):
    return {
        "schema_version": DATA_SCHEMA_VERSION,
        "data_type": data_type,
        "generated_at": datetime.now().isoformat(),
        "version_signature": _generate_version_signature(context, data_type),
        "context_digest": {
            "商圈": context.get("district"),
            "时段": context.get("time_slot"),
            "天气": context.get("weather"),
            "日期": str(context.get("selected_date")),
            "是否高峰期": context.get("is_peak"),
            "天气影响系数": context.get("weather_factor")
        }
    }


def get_district_responsible(district):
    return DISTRICT_RESPONSIBLE.get(district, "未分配责任人")


def get_all_district_responsibles():
    return DISTRICT_RESPONSIBLE.copy()


def generate_business_context(selected_date=None, district=None, weather=None, time_slot=None):
    if selected_date is None:
        selected_date = datetime.now().date()
    if district is None:
        district = random.choice(BUSINESS_DISTRICTS)
    if weather is None:
        weather = random.choice(WEATHER_TYPES)
    if time_slot is None:
        time_slot = random.choice(TIME_SLOTS)

    is_peak = time_slot in PEAK_SLOTS
    weather_factor = WEATHER_IMPACT_FACTOR.get(weather, 1.0)

    district_base_order = {
        "中关村商圈": 800, "国贸商圈": 1200, "望京商圈": 900, "三里屯商圈": 1000,
        "西单商圈": 1100, "朝阳大悦城商圈": 950, "五道口商圈": 700, "亦庄商圈": 600
    }

    district_base_rider = {
        "中关村商圈": 60, "国贸商圈": 90, "望京商圈": 70, "三里屯商圈": 75,
        "西单商圈": 85, "朝阳大悦城商圈": 70, "五道口商圈": 50, "亦庄商圈": 45
    }

    base_orders = district_base_order.get(district, 800)
    base_riders = district_base_rider.get(district, 60)

    peak_multiplier = 1.8 if is_peak else 1.0

    context = {
        "selected_date": selected_date,
        "district": district,
        "weather": weather,
        "time_slot": time_slot,
        "is_peak": is_peak,
        "weather_factor": weather_factor,
        "peak_multiplier": peak_multiplier,
        "base_orders": base_orders,
        "base_riders": base_riders,
        "current_responsible": get_district_responsible(district),
        "timestamp": datetime.now().isoformat()
    }
    return context


def generate_hotspot_data(context):
    district = context["district"]
    weather_factor = context["weather_factor"]
    peak_multiplier = context["peak_multiplier"]
    base_orders = context["base_orders"]

    sub_areas = [f"{district}-{i}区" for i in range(1, 7)]
    orders = []
    for i, area in enumerate(sub_areas):
        area_factor = 0.5 + (i % 3) * 0.3 + random.uniform(-0.1, 0.1)
        order_count = int(base_orders * 0.18 * area_factor * weather_factor * peak_multiplier)
        merchant_density = round(0.3 + i * 0.12, 2)
        est_delivery = int(30 + (6 - i) * 5 + (weather_factor - 1) * 15)
        rider_allocated = int(context["base_riders"] * 0.15)
        supply_ratio = round(order_count / max(rider_allocated, 1), 2)

        if supply_ratio > 3.0:
            level = "高热区"
        elif supply_ratio > 1.5:
            level = "正常"
        else:
            level = "低负荷"

        orders.append({
            "看板维度": "订单热区",
            "子区域": area,
            "所属商圈": district,
            "订单量": order_count,
            "预计送达时长(分钟)": est_delivery,
            "商户密度": merchant_density,
            "配属骑手数": rider_allocated,
            "供需比": supply_ratio,
            "热区等级": level,
            "天气影响系数": weather_factor,
            "是否高峰期": "是" if context["is_peak"] else "否",
            "分析时段": context["time_slot"],
            "责任人": get_district_responsible(district)
        })

    df = pd.DataFrame(orders)

    version_trace = _build_version_trace(context, "订单热区分析")
    summary = {
        "总子区域数": len(df),
        "高热区数量": int((df["热区等级"] == "高热区").sum()),
        "正常区域数": int((df["热区等级"] == "正常").sum()),
        "低负荷区域数": int((df["热区等级"] == "低负荷").sum()),
        "总订单量": int(df["订单量"].sum()),
        "平均供需比": round(float(df["供需比"].mean()), 2),
        "最高供需比区域": df.loc[df["供需比"].idxmax(), "子区域"],
        "最高供需比": round(float(df["供需比"].max()), 2)
    }

    return {
        "data": df,
        "version_trace": version_trace,
        "summary": summary
    }


def _detect_rider_anomalies(rider_stats, context):
    anomalies = []
    total = rider_stats["总注册骑手"]
    online = rider_stats["在线骑手"]
    delivering = rider_stats["配送中骑手"]
    idle = rider_stats["空闲骑手"]
    expected_drop = rider_stats.get("预计离线人数", 0)

    online_ratio = online / max(total, 1)
    delivery_ratio = delivering / max(online, 1)
    drop_rate = expected_drop / max(total, 1)

    if online_ratio < RIDER_ANOMALY_THRESHOLDS["min_online_ratio"]:
        anomalies.append({
            "异常类型": "在线率过低",
            "异常描述": f"当前在线率仅 {round(online_ratio * 100, 1)}%，低于阈值 {RIDER_ANOMALY_THRESHOLDS['min_online_ratio'] * 100}%",
            "严重程度": "高危",
            "建议动作": "立即联系休息骑手紧急上线，或申请跨商圈支援"
        })

    if idle < RIDER_ANOMALY_THRESHOLDS["min_idle_riders"]:
        anomalies.append({
            "异常类型": "空闲骑手不足",
            "异常描述": f"当前空闲骑手仅 {idle} 人，低于阈值 {RIDER_ANOMALY_THRESHOLDS['min_idle_riders']} 人",
            "严重程度": "警告",
            "建议动作": "优先调度配送中骑手完成当前订单后待命"
        })

    if delivery_ratio > RIDER_ANOMALY_THRESHOLDS["max_delivery_ratio"]:
        anomalies.append({
            "异常类型": "配送过载",
            "异常描述": f"配送中骑手占比 {round(delivery_ratio * 100, 1)}%，超过阈值 {RIDER_ANOMALY_THRESHOLDS['max_delivery_ratio'] * 100}%",
            "严重程度": "警告",
            "建议动作": "评估是否减少接单或增加临时骑手"
        })

    if drop_rate > RIDER_ANOMALY_THRESHOLDS["max_drop_rate"]:
        anomalies.append({
            "异常类型": "离线率异常偏高",
            "异常描述": f"预计离线率 {round(drop_rate * 100, 1)}%，超过阈值 {RIDER_ANOMALY_THRESHOLDS['max_drop_rate'] * 100}%",
            "严重程度": "高危",
            "建议动作": "核查离线原因，是否存在系统故障或集体异常"
        })

    return anomalies


def generate_rider_data(context):
    base_riders = context["base_riders"]
    weather_factor = context["weather_factor"]
    is_peak = context["is_peak"]

    force_anomaly = random.random() < 0.3

    if force_anomaly:
        anomaly_mode = random.choice(["low_online", "low_idle", "overload"])
        if anomaly_mode == "low_online":
            total_riders = int(base_riders * (0.9 if is_peak else 0.7) / weather_factor)
            online_riders = int(total_riders * random.uniform(0.3, 0.45))
        elif anomaly_mode == "low_idle":
            total_riders = int(base_riders * (0.9 if is_peak else 0.7) / weather_factor)
            online_riders = int(total_riders * random.uniform(0.85, 0.95))
        else:
            total_riders = int(base_riders * (0.9 if is_peak else 0.7) / weather_factor)
            online_riders = int(total_riders * random.uniform(0.85, 0.95))
    else:
        total_riders = int(base_riders * (0.9 if is_peak else 0.7) / weather_factor)
        online_riders = int(total_riders * random.uniform(0.85, 0.95))

    if force_anomaly and anomaly_mode == "overload":
        delivering_riders = int(online_riders * random.uniform(0.93, 0.98))
    elif force_anomaly and anomaly_mode == "low_idle":
        delivering_riders = int(online_riders * random.uniform(0.95, 0.99))
    else:
        delivering_riders = int(online_riders * random.uniform(0.65, 0.80))

    idle_riders = online_riders - delivering_riders
    offline_riders = total_riders - online_riders
    expected_offline = max(0, offline_riders - int(base_riders * 0.05))

    rider_status = pd.DataFrame({
        "看板维度": "骑手在线",
        "状态": ["在线配送中", "在线空闲", "离线"],
        "人数": [delivering_riders, idle_riders, offline_riders],
        "占比(%)": [
            round(delivering_riders / max(total_riders, 1) * 100, 1),
            round(idle_riders / max(total_riders, 1) * 100, 1),
            round(offline_riders / max(total_riders, 1) * 100, 1)
        ]
    })

    avg_delivery_per_rider = round(
        context["base_orders"] * context["weather_factor"] * context["peak_multiplier"] / max(online_riders, 1), 1
    )

    recent_trend = []
    for i in range(12):
        factor = 0.9 + (i % 4) * 0.05 + random.uniform(-0.03, 0.03)
        recent_trend.append({
            "看板维度": "骑手在线",
            "时间点": f"{i * 5}分钟前",
            "在线骑手数": int(online_riders * factor),
            "配送中骑手数": int(delivering_riders * factor),
            "空闲骑手数": max(0, int(online_riders * factor) - int(delivering_riders * factor))
        })
    trend_df = pd.DataFrame(recent_trend[::-1])

    rider_stats = {
        "总注册骑手": total_riders,
        "在线骑手": online_riders,
        "配送中骑手": delivering_riders,
        "空闲骑手": idle_riders,
        "离线骑手": offline_riders,
        "预计离线人数": expected_offline
    }

    anomalies = _detect_rider_anomalies(rider_stats, context)

    result = {
        "总注册骑手": total_riders,
        "在线骑手": online_riders,
        "配送中骑手": delivering_riders,
        "空闲骑手": idle_riders,
        "离线骑手": offline_riders,
        "人均配送单量": avg_delivery_per_rider,
        "在线率(%)": round(online_riders / max(total_riders, 1) * 100, 1),
        "配送负载率(%)": round(delivering_riders / max(online_riders, 1) * 100, 1),
        "骑手状态分布": rider_status,
        "近期趋势": trend_df,
        "异常检测": {
            "是否异常": len(anomalies) > 0,
            "异常数量": len(anomalies),
            "异常列表": anomalies,
            "当前责任人": get_district_responsible(context["district"]),
            "责任人联系建议": f"请立即联系【{get_district_responsible(context['district'])}】处理骑手在线异常"
        },
        "看板维度信息": {
            "看板维度": "骑手在线",
            "所属商圈": context["district"],
            "分析时段": context["time_slot"],
            "天气状况": context["weather"],
            "是否高峰期": "是" if is_peak else "否"
        }
    }

    version_trace = _build_version_trace(context, "骑手在线分析")
    result["version_trace"] = version_trace

    return result


def generate_timeout_data(context):
    weather_factor = context["weather_factor"]
    is_peak = context["is_peak"]
    peak_multiplier = context["peak_multiplier"]

    base_timeout_rate = 0.05
    timeout_rate = min(
        base_timeout_rate * weather_factor * (1.5 if is_peak else 1.0),
        0.35
    )

    total_orders = int(context["base_orders"] * weather_factor * peak_multiplier)
    timeout_orders = int(total_orders * timeout_rate)

    timeout_reasons = pd.DataFrame({
        "看板维度": "超时率",
        "原因": ["天气恶劣", "骑手不足", "商户出餐慢", "地址异常", "交通拥堵"],
        "占比": [
            round(0.15 + (weather_factor - 1) * 0.3, 3),
            round(0.25 + (peak_multiplier - 1) * 0.1, 3),
            round(0.25 + random.uniform(-0.05, 0.05), 3),
            round(0.15 + random.uniform(-0.03, 0.03), 3),
            round(0.20 + (weather_factor - 1) * 0.1, 3)
        ]
    })
    timeout_reasons["占比"] = round(timeout_reasons["占比"] / timeout_reasons["占比"].sum(), 3)
    timeout_reasons["订单数"] = (timeout_reasons["占比"] * timeout_orders).astype(int)
    timeout_reasons["占比(%)"] = (timeout_reasons["占比"] * 100).round(1)

    recent_timeout = []
    for day in range(7, 0, -1):
        day_factor = 0.8 + (8 - day) * 0.03 + random.uniform(-0.05, 0.05)
        recent_timeout.append({
            "看板维度": "超时率",
            "日期": (datetime.now() - timedelta(days=day)).strftime("%m-%d"),
            "超时率": round(timeout_rate * day_factor, 4),
            "超时率(%)": round(timeout_rate * day_factor * 100, 2)
        })
    trend_df = pd.DataFrame(recent_timeout)

    result = {
        "总订单数": total_orders,
        "超时订单数": timeout_orders,
        "超时率": round(timeout_rate, 4),
        "超时率(%)": round(timeout_rate * 100, 2),
        "超时判定阈值": 0.08,
        "超时判定阈值(%)": 8.0,
        "是否超标": timeout_rate > 0.08,
        "判定结果": "超标" if timeout_rate > 0.08 else "正常",
        "超时原因分布": timeout_reasons,
        "近7日趋势": trend_df,
        "看板维度信息": {
            "看板维度": "超时率",
            "所属商圈": context["district"],
            "分析时段": context["time_slot"],
            "天气状况": context["weather"],
            "天气影响系数": weather_factor,
            "是否高峰期": "是" if is_peak else "否"
        }
    }

    version_trace = _build_version_trace(context, "超时率分析")
    result["version_trace"] = version_trace

    return result


def generate_weather_data(context):
    weather = context["weather"]
    weather_factor = context["weather_factor"]

    comparison = pd.DataFrame({
        "看板维度": "天气影响",
        "天气类型": WEATHER_TYPES,
        "影响系数": [WEATHER_IMPACT_FACTOR[w] for w in WEATHER_TYPES],
        "预估订单增量": [f"{int((WEATHER_IMPACT_FACTOR[w] - 1) * 100)}%" for w in WEATHER_TYPES],
        "预估配送时长增加": [f"{int((WEATHER_IMPACT_FACTOR[w] - 1) * 20)}分钟" for w in WEATHER_TYPES],
        "影响等级": ["轻微" if WEATHER_IMPACT_FACTOR[w] <= 1.1 else
                    "中等" if WEATHER_IMPACT_FACTOR[w] <= 1.5 else "严重"
                    for w in WEATHER_TYPES]
    })

    rider_supply_advice = "增加" if weather_factor > 1.2 else "正常"
    subsidy_advice = "建议天气补贴" if weather_factor > 1.3 else "无需额外补贴"

    impact_summary = {
        "当前天气": weather,
        "影响系数": weather_factor,
        "订单增量预估": f"{int((weather_factor - 1) * 100)}%",
        "配送时长增加": f"{int((weather_factor - 1) * 20)}分钟",
        "骑手供给建议": rider_supply_advice,
        "补贴建议": subsidy_advice,
        "影响等级": "轻微" if weather_factor <= 1.1 else "中等" if weather_factor <= 1.5 else "严重",
        "是否恶劣天气": weather_factor > 1.2
    }

    hourly_data = []
    for slot in TIME_SLOTS:
        slot_factor = 1.5 if slot in PEAK_SLOTS else 1.0
        is_slot_peak = slot in PEAK_SLOTS
        hourly_data.append({
            "看板维度": "天气影响",
            "时段": slot,
            "是否高峰期": "是" if is_slot_peak else "否",
            "天气影响订单量": int(context["base_orders"] * 0.15 * weather_factor * slot_factor),
            "天气影响超时率": round(0.05 * weather_factor * slot_factor, 4),
            "天气影响超时率(%)": round(0.05 * weather_factor * slot_factor * 100, 2),
            "综合影响系数": round(weather_factor * slot_factor, 2)
        })
    hourly_df = pd.DataFrame(hourly_data)

    result = {
        "影响摘要": impact_summary,
        "天气对比表": comparison,
        "分时段影响": hourly_df,
        "看板维度信息": {
            "看板维度": "天气影响",
            "所属商圈": context["district"],
            "分析时段": context["time_slot"],
            "当前天气": weather,
            "天气影响系数": weather_factor,
            "骑手供给建议": rider_supply_advice,
            "补贴建议": subsidy_advice
        }
    }

    version_trace = _build_version_trace(context, "天气影响分析")
    result["version_trace"] = version_trace

    return result


def detect_peak_warning(context, hotspot_data, rider_data, timeout_data):
    warnings = []
    warning_level = "正常"

    hotspot_df = hotspot_data["data"] if isinstance(hotspot_data, dict) and "data" in hotspot_data else hotspot_data

    supply_demand_ratio = timeout_data["总订单数"] / max(rider_data["在线骑手"], 1)

    if supply_demand_ratio > 15 or timeout_data["超时率"] > 0.15:
        warning_level = "严重"
    elif supply_demand_ratio > 10 or timeout_data["超时率"] > 0.08 or context["weather_factor"] > 1.5:
        warning_level = "警告"

    if supply_demand_ratio > 10:
        warnings.append(f"供需比过高: {round(supply_demand_ratio, 1)}单/骑手 (阈值: 10)")
    if timeout_data["超时率"] > 0.08:
        warnings.append(f"超时率超标: {round(timeout_data['超时率'] * 100, 2)}% (阈值: 8%)")
    if context["weather_factor"] > 1.3:
        warnings.append(f"恶劣天气影响: {context['weather']} (系数: {context['weather_factor']})")
    if rider_data["空闲骑手"] < 5:
        warnings.append(f"空闲骑手不足: {rider_data['空闲骑手']}人")

    rider_anomaly = rider_data.get("异常检测", {})
    if rider_anomaly.get("是否异常"):
        warnings.append(f"骑手在线异常: 检测到{rider_anomaly['异常数量']}项异常，责任人【{rider_anomaly['当前责任人']}】")

    high_hotspots = hotspot_df[hotspot_df["热区等级"] == "高热区"]["子区域"].tolist()
    if high_hotspots:
        warnings.append(f"高热区数量: {len(high_hotspots)}个 ({', '.join(high_hotspots[:3])})")

    return {
        "预警级别": warning_level,
        "预警内容": warnings if warnings else ["当前供需平衡，无预警"],
        "供需比": round(supply_demand_ratio, 1),
        "检测时间": datetime.now().isoformat(),
        "上下文摘要": {
            "商圈": context["district"],
            "时段": context["time_slot"],
            "天气": context["weather"],
            "是否高峰期": context["is_peak"],
            "当前责任人": get_district_responsible(context["district"])
        },
        "骑手异常摘要": rider_anomaly
    }


def generate_subsidy_suggestion(context, warning_info):
    level = warning_info["预警级别"]
    weather = context["weather"]
    is_peak = context["is_peak"]

    subsidies = []

    if level == "严重":
        subsidies.append({"类型": "峰值补贴", "金额(元/单)": 3.0, "适用范围": "全商圈", "持续时间": "2小时"})
        subsidies.append({"类型": "天气补贴", "金额(元/单)": 2.5, "适用范围": "全商圈", "持续时间": "天气持续期间"})
    elif level == "警告":
        subsidies.append({"类型": "峰值补贴", "金额(元/单)": 1.5, "适用范围": "高热区", "持续时间": "1小时"})
        if context["weather_factor"] > 1.2:
            subsidies.append({"类型": "天气补贴", "金额(元/单)": 1.0, "适用范围": "全商圈", "持续时间": "天气持续期间"})
    else:
        subsidies.append({"类型": "常规补贴", "金额(元/单)": 0.0, "适用范围": "无", "持续时间": "无"})

    if is_peak:
        subsidies.append({"类型": "高峰期激励", "金额(元/单)": 1.0, "适用范围": "全商圈", "持续时间": context["time_slot"]})

    return {
        "预警级别": level,
        "补贴策略": subsidies,
        "生成时间": datetime.now().isoformat(),
        "上下文摘要": {
            "商圈": context["district"],
            "时段": context["time_slot"],
            "天气": weather,
            "供需比": warning_info["供需比"],
            "责任人": get_district_responsible(context["district"])
        }
    }
