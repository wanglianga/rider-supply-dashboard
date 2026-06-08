import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

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


def generate_business_context(selected_date=None, district=None, weather=None, time_slot=None):
    """生成统一的业务上下文，所有数据模块共享"""
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
        "timestamp": datetime.now().isoformat()
    }
    return context


def generate_hotspot_data(context):
    """基于业务上下文生成订单热区数据"""
    district = context["district"]
    weather_factor = context["weather_factor"]
    peak_multiplier = context["peak_multiplier"]
    base_orders = context["base_orders"]

    sub_areas = [f"{district}-{i}区" for i in range(1, 7)]
    orders = []
    for i, area in enumerate(sub_areas):
        area_factor = 0.5 + (i % 3) * 0.3 + random.uniform(-0.1, 0.1)
        order_count = int(base_orders * 0.18 * area_factor * weather_factor * peak_multiplier)
        orders.append({
            "子区域": area,
            "订单量": order_count,
            "预计送达时长(分钟)": int(30 + (6 - i) * 5 + (weather_factor - 1) * 15),
            "商户密度": round(0.3 + i * 0.12, 2)
        })

    df = pd.DataFrame(orders)
    df["供需比"] = round(df["订单量"] / (context["base_riders"] * 0.15), 2)
    df["热区等级"] = pd.cut(
        df["供需比"],
        bins=[0, 1.5, 3.0, float("inf")],
        labels=["低负荷", "正常", "高热区"]
    )
    return df


def generate_rider_data(context):
    """基于业务上下文生成骑手在线数据"""
    base_riders = context["base_riders"]
    weather_factor = context["weather_factor"]
    is_peak = context["is_peak"]

    total_riders = int(base_riders * (0.9 if is_peak else 0.7) / weather_factor)
    online_riders = int(total_riders * random.uniform(0.85, 0.95))
    delivering_riders = int(online_riders * random.uniform(0.65, 0.80))
    idle_riders = online_riders - delivering_riders

    rider_status = pd.DataFrame({
        "状态": ["在线配送中", "在线空闲", "离线"],
        "人数": [delivering_riders, idle_riders, total_riders - online_riders]
    })

    avg_delivery_per_rider = round(
        context["base_orders"] * context["weather_factor"] * context["peak_multiplier"] / max(online_riders, 1), 1
    )

    recent_trend = []
    for i in range(12):
        factor = 0.9 + (i % 4) * 0.05 + random.uniform(-0.03, 0.03)
        recent_trend.append({
            "时间点": f"{i * 5}分钟前",
            "在线骑手数": int(online_riders * factor),
            "配送中骑手数": int(delivering_riders * factor)
        })
    trend_df = pd.DataFrame(recent_trend[::-1])

    return {
        "总注册骑手": total_riders,
        "在线骑手": online_riders,
        "配送中骑手": delivering_riders,
        "空闲骑手": idle_riders,
        "人均配送单量": avg_delivery_per_rider,
        "骑手状态分布": rider_status,
        "近期趋势": trend_df
    }


def generate_timeout_data(context):
    """基于业务上下文生成超时率数据"""
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

    recent_timeout = []
    for day in range(7, 0, -1):
        day_factor = 0.8 + (8 - day) * 0.03 + random.uniform(-0.05, 0.05)
        recent_timeout.append({
            "日期": (datetime.now() - timedelta(days=day)).strftime("%m-%d"),
            "超时率": round(timeout_rate * day_factor, 4)
        })
    trend_df = pd.DataFrame(recent_timeout)

    return {
        "总订单数": total_orders,
        "超时订单数": timeout_orders,
        "超时率": round(timeout_rate, 4),
        "超时判定阈值": 0.08,
        "是否超标": timeout_rate > 0.08,
        "超时原因分布": timeout_reasons,
        "近7日趋势": trend_df
    }


def generate_weather_data(context):
    """基于业务上下文生成天气影响数据"""
    weather = context["weather"]
    weather_factor = context["weather_factor"]

    comparison = pd.DataFrame({
        "天气类型": WEATHER_TYPES,
        "影响系数": [WEATHER_IMPACT_FACTOR[w] for w in WEATHER_TYPES],
        "预估订单增量": [f"{int((WEATHER_IMPACT_FACTOR[w] - 1) * 100)}%" for w in WEATHER_TYPES],
        "预估配送时长增加": [f"{int((WEATHER_IMPACT_FACTOR[w] - 1) * 20)}分钟" for w in WEATHER_TYPES]
    })

    impact_summary = {
        "当前天气": weather,
        "影响系数": weather_factor,
        "订单增量预估": f"{int((weather_factor - 1) * 100)}%",
        "配送时长增加": f"{int((weather_factor - 1) * 20)}分钟",
        "骑手供给建议": "增加" if weather_factor > 1.2 else "正常",
        "补贴建议": "建议天气补贴" if weather_factor > 1.3 else "无需额外补贴"
    }

    hourly_data = []
    for slot in TIME_SLOTS:
        slot_factor = 1.5 if slot in PEAK_SLOTS else 1.0
        hourly_data.append({
            "时段": slot,
            "天气影响订单量": int(context["base_orders"] * 0.15 * weather_factor * slot_factor),
            "天气影响超时率": round(0.05 * weather_factor * slot_factor, 4)
        })
    hourly_df = pd.DataFrame(hourly_data)

    return {
        "影响摘要": impact_summary,
        "天气对比表": comparison,
        "分时段影响": hourly_df
    }


def detect_peak_warning(context, hotspot_df, rider_data, timeout_data):
    """峰值预警检测"""
    warnings = []
    warning_level = "正常"

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
            "是否高峰期": context["is_peak"]
        }
    }


def generate_subsidy_suggestion(context, warning_info):
    """生成补贴策略建议"""
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
            "供需比": warning_info["供需比"]
        }
    }
