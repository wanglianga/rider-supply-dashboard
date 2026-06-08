import argparse
import json
import sys
from datetime import datetime, date
from data_generator import (
    BUSINESS_DISTRICTS, WEATHER_TYPES, TIME_SLOTS,
    generate_business_context, generate_hotspot_data,
    generate_rider_data, generate_timeout_data,
    generate_weather_data, detect_peak_warning,
    generate_subsidy_suggestion, get_district_responsible,
    get_all_district_responsibles, DATA_SCHEMA_VERSION
)


def print_separator(title=""):
    width = 70
    if title:
        line = f"{'=' * 10} {title} {'=' * (width - len(title) - 12)}"
    else:
        line = "=" * width
    print(line)


def format_context_summary(ctx):
    return {
        "商圈": ctx["district"],
        "时段": ctx["time_slot"],
        "天气": ctx["weather"],
        "是否高峰期": ctx["is_peak"],
        "天气影响系数": ctx["weather_factor"],
        "当前责任人": get_district_responsible(ctx["district"])
    }


def verify_hotspot(hotspot_wrapper):
    hotspot_df = hotspot_wrapper["data"]
    version = hotspot_wrapper["version_trace"]
    summary = hotspot_wrapper["summary"]

    checks = []

    expected_fields = [
        "看板维度", "子区域", "所属商圈", "订单量", "预计送达时长(分钟)",
        "商户密度", "配属骑手数", "供需比", "热区等级",
        "天气影响系数", "是否高峰期", "分析时段", "责任人"
    ]
    missing_fields = [f for f in expected_fields if f not in hotspot_df.columns]
    checks.append({
        "检查项": "订单热区字段完整性",
        "状态": "PASS" if not missing_fields else "FAIL",
        "详情": "所有字段齐全" if not missing_fields else f"缺少字段: {missing_fields}"
    })

    valid_levels = {"低负荷", "正常", "高热区"}
    invalid_levels = set(hotspot_df["热区等级"].unique()) - valid_levels
    checks.append({
        "检查项": "热区等级合法性",
        "状态": "PASS" if not invalid_levels else "FAIL",
        "详情": f"等级分布正常: {hotspot_df['热区等级'].value_counts().to_dict()}" if not invalid_levels else f"非法等级: {invalid_levels}"
    })

    version_checks = ["schema_version", "data_type", "generated_at", "version_signature", "context_digest"]
    missing_version = [k for k in version_checks if k not in version]
    checks.append({
        "检查项": "版本痕迹完整性",
        "状态": "PASS" if not missing_version else "FAIL",
        "详情": f"版本签名: {version.get('version_signature', 'N/A')}, Schema: {version.get('schema_version', 'N/A')}" if not missing_version else f"缺失: {missing_version}"
    })

    checks.append({
        "检查项": "热区摘要统计",
        "状态": "PASS",
        "详情": json.dumps(summary, ensure_ascii=False)
    })

    return checks


def verify_rider(rider_data):
    checks = []

    expected_keys = [
        "总注册骑手", "在线骑手", "配送中骑手", "空闲骑手", "离线骑手",
        "人均配送单量", "在线率(%)", "配送负载率(%)",
        "骑手状态分布", "近期趋势", "异常检测", "看板维度信息", "version_trace"
    ]
    missing_keys = [k for k in expected_keys if k not in rider_data]
    checks.append({
        "检查项": "骑手数据字段完整性",
        "状态": "PASS" if not missing_keys else "FAIL",
        "详情": "所有字段齐全" if not missing_keys else f"缺少字段: {missing_keys}"
    })

    anomaly = rider_data["异常检测"]
    checks.append({
        "检查项": "骑手异常检测功能",
        "状态": "PASS",
        "详情": (
            f"是否异常: {anomaly['是否异常']}, "
            f"异常数量: {anomaly['异常数量']}, "
            f"当前责任人: {anomaly['当前责任人']}"
        )
    })

    if anomaly["是否异常"]:
        for idx, a in enumerate(anomaly["异常列表"], 1):
            checks.append({
                "检查项": f"  异常项{idx}: {a['异常类型']}",
                "状态": "DETECTED",
                "详情": f"严重程度: {a['严重程度']} | {a['异常描述']} | 建议: {a['建议动作']}"
            })

    total = rider_data["总注册骑手"]
    online = rider_data["在线骑手"]
    delivering = rider_data["配送中骑手"]
    idle = rider_data["空闲骑手"]
    offline = rider_data["离线骑手"]
    num_consistent = (delivering + idle == online) and (online + offline == total)
    checks.append({
        "检查项": "骑手人数逻辑一致性",
        "状态": "PASS" if num_consistent else "FAIL",
        "详情": (
            f"总注册={total}, 在线={online}, 配送中={delivering}, "
            f"空闲={idle}, 离线={offline}"
        )
    })

    version = rider_data.get("version_trace", {})
    checks.append({
        "检查项": "骑手版本痕迹",
        "状态": "PASS" if version else "FAIL",
        "详情": f"版本签名: {version.get('version_signature', 'N/A')}" if version else "无版本痕迹"
    })

    return checks


def verify_weather(weather_data):
    checks = []

    impact = weather_data["影响摘要"]
    expected_impact = ["当前天气", "影响系数", "订单增量预估", "配送时长增加", "骑手供给建议", "补贴建议", "影响等级", "是否恶劣天气"]
    missing_impact = [k for k in expected_impact if k not in impact]
    checks.append({
        "检查项": "天气影响摘要字段",
        "状态": "PASS" if not missing_impact else "FAIL",
        "详情": f"天气={impact['当前天气']}, 系数=x{impact['影响系数']}, 等级={impact['影响等级']}" if not missing_impact else f"缺失: {missing_impact}"
    })

    comparison = weather_data["天气对比表"]
    expected_comp = ["看板维度", "天气类型", "影响系数", "预估订单增量", "预估配送时长增加", "影响等级"]
    missing_comp = [f for f in expected_comp if f not in comparison.columns]
    checks.append({
        "检查项": "天气对比表字段",
        "状态": "PASS" if not missing_comp else "FAIL",
        "详情": f"共 {len(comparison)} 种天气类型" if not missing_comp else f"缺失: {missing_comp}"
    })

    hourly = weather_data["分时段影响"]
    expected_hourly = ["看板维度", "时段", "是否高峰期", "天气影响订单量", "天气影响超时率", "天气影响超时率(%)", "综合影响系数"]
    missing_hourly = [f for f in expected_hourly if f not in hourly.columns]
    checks.append({
        "检查项": "分时段天气影响字段",
        "状态": "PASS" if not missing_hourly else "FAIL",
        "详情": f"共 {len(hourly)} 个时段" if not missing_hourly else f"缺失: {missing_hourly}"
    })

    version = weather_data.get("version_trace", {})
    checks.append({
        "检查项": "天气版本痕迹",
        "状态": "PASS" if version else "FAIL",
        "详情": f"版本签名: {version.get('version_signature', 'N/A')}" if version else "无版本痕迹"
    })

    return checks


def verify_timeout(timeout_data):
    checks = []

    checks.append({
        "检查项": "超时率基础指标",
        "状态": "PASS",
        "详情": (
            f"总订单={timeout_data['总订单数']}, "
            f"超时订单={timeout_data['超时订单数']}, "
            f"超时率={timeout_data['超时率(%)']}%, "
            f"阈值={timeout_data['超时判定阈值(%)']}%, "
            f"判定={timeout_data['判定结果']}"
        )
    })

    rate_consistent = abs(timeout_data["超时率"] * 100 - timeout_data["超时率(%)"]) < 0.01
    checks.append({
        "检查项": "超时率数据一致性",
        "状态": "PASS" if rate_consistent else "FAIL",
        "详情": f"小数={timeout_data['超时率']}, 百分比={timeout_data['超时率(%)']}%"
    })

    version = timeout_data.get("version_trace", {})
    checks.append({
        "检查项": "超时率版本痕迹",
        "状态": "PASS" if version else "FAIL",
        "详情": f"版本签名: {version.get('version_signature', 'N/A')}" if version else "无版本痕迹"
    })

    return checks


def verify_warning(warning_info):
    checks = []

    expected = ["预警级别", "预警内容", "供需比", "检测时间", "上下文摘要"]
    missing = [k for k in expected if k not in warning_info]
    checks.append({
        "检查项": "预警字段完整性",
        "状态": "PASS" if not missing else "FAIL",
        "详情": f"级别={warning_info.get('预警级别', 'N/A')}, 供需比={warning_info.get('供需比', 'N/A')}" if not missing else f"缺失: {missing}"
    })

    ctx = warning_info.get("上下文摘要", {})
    checks.append({
        "检查项": "预警责任人信息",
        "状态": "PASS" if "当前责任人" in ctx else "FAIL",
        "详情": f"责任人: {ctx.get('当前责任人', '缺失')}"
    })

    rider_anomaly = warning_info.get("骑手异常摘要", {})
    if rider_anomaly:
        checks.append({
            "检查项": "预警骑手异常摘要",
            "状态": "PASS",
            "详情": f"是否异常={rider_anomaly.get('是否异常')}, 异常数={rider_anomaly.get('异常数量')}"
        })

    return checks


def run_full_verification(district=None, weather=None, time_slot=None, verbose=False):
    print_separator("外卖商圈骑手供需分析看板 - 命令行验证")
    print(f"验证时间: {datetime.now().isoformat()}")
    print(f"Schema 版本: {DATA_SCHEMA_VERSION}")
    print()

    ctx = generate_business_context(
        district=district,
        weather=weather,
        time_slot=time_slot
    )

    print_separator("业务上下文")
    for k, v in format_context_summary(ctx).items():
        print(f"  {k}: {v}")
    print()

    hotspot = generate_hotspot_data(ctx)
    rider = generate_rider_data(ctx)
    timeout = generate_timeout_data(ctx)
    weather_data = generate_weather_data(ctx)
    warning = detect_peak_warning(ctx, hotspot, rider, timeout)
    subsidy = generate_subsidy_suggestion(ctx, warning)

    all_checks = []

    print_separator("1. 订单热区验证")
    hs_checks = verify_hotspot(hotspot)
    for c in hs_checks:
        status_icon = "[PASS]" if c["状态"] == "PASS" else "[FAIL]" if c["状态"] == "FAIL" else "[INFO]"
        print(f"  {status_icon} {c['检查项']}: {c['详情']}")
    all_checks.extend(hs_checks)
    print()

    print_separator("2. 骑手在线验证（含异常检测与责任人）")
    rd_checks = verify_rider(rider)
    for c in rd_checks:
        status_icon = "[PASS]" if c["状态"] == "PASS" else "[FAIL]" if c["状态"] == "FAIL" else "[INFO]" if c["状态"] == "DETECTED" else "[WARN]"
        print(f"  {status_icon} {c['检查项']}: {c['详情']}")
    all_checks.extend(rd_checks)
    print()

    print_separator("3. 天气影响验证")
    wt_checks = verify_weather(weather_data)
    for c in wt_checks:
        status_icon = "[PASS]" if c["状态"] == "PASS" else "[FAIL]"
        print(f"  {status_icon} {c['检查项']}: {c['详情']}")
    all_checks.extend(wt_checks)
    print()

    print_separator("4. 超时率验证")
    to_checks = verify_timeout(timeout)
    for c in to_checks:
        status_icon = "[PASS]" if c["状态"] == "PASS" else "[FAIL]"
        print(f"  {status_icon} {c['检查项']}: {c['详情']}")
    all_checks.extend(to_checks)
    print()

    print_separator("5. 峰值预警验证")
    wn_checks = verify_warning(warning)
    for c in wn_checks:
        status_icon = "[PASS]" if c["状态"] == "PASS" else "[FAIL]"
        print(f"  {status_icon} {c['检查项']}: {c['详情']}")
    all_checks.extend(wn_checks)
    print()

    print_separator("责任人汇总")
    all_resp = get_all_district_responsibles()
    for d, r in all_resp.items():
        marker = " <-- 当前" if d == ctx["district"] else ""
        print(f"  {d}: {r}{marker}")
    print()

    print_separator("验证摘要")
    total = len(all_checks)
    passed = sum(1 for c in all_checks if c["状态"] == "PASS")
    failed = sum(1 for c in all_checks if c["状态"] == "FAIL")
    detected = sum(1 for c in all_checks if c["状态"] == "DETECTED")
    print(f"  总检查项: {total}")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    if detected:
        print(f"  检测到异常: {detected} 项")

    print()
    print(f"  全局责任人: {get_district_responsible(ctx['district'])}")
    rider_anomaly = rider["异常检测"]
    if rider_anomaly["是否异常"]:
        print(f"  骑手异常状态: 检测到 {rider_anomaly['异常数量']} 项异常")
        print(f"  责任人联系建议: {rider_anomaly['责任人联系建议']}")
    else:
        print("  骑手异常状态: 正常")

    print(f"  预警级别: {warning['预警级别']}")
    print(f"  供需比: {warning['供需比']} 单/骑手")

    print_separator()

    return {
        "verification_time": datetime.now().isoformat(),
        "schema_version": DATA_SCHEMA_VERSION,
        "context": format_context_summary(ctx),
        "summary": {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "anomalies_detected": detected
        },
        "rider_anomaly": rider["异常检测"],
        "warning_level": warning["预警级别"],
        "supply_demand_ratio": warning["供需比"],
        "all_checks": all_checks if verbose else None
    }


def main():
    parser = argparse.ArgumentParser(
        description="外卖商圈骑手供需分析看板 - 命令行验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py
  python cli.py --district 国贸商圈 --weather 大雨 --time-slot 11:00-13:00
  python cli.py --json
  python cli.py --verbose
        """
    )
    parser.add_argument("--district", choices=BUSINESS_DISTRICTS, help="指定商圈")
    parser.add_argument("--weather", choices=WEATHER_TYPES, help="指定天气状况")
    parser.add_argument("--time-slot", choices=TIME_SLOTS, help="指定分析时段")
    parser.add_argument("--json", action="store_true", help="以JSON格式输出结果")
    parser.add_argument("--verbose", action="store_true", help="输出详细检查项列表")

    args = parser.parse_args()

    result = run_full_verification(
        district=args.district,
        weather=args.weather,
        time_slot=args.time_slot,
        verbose=args.verbose
    )

    if args.json:
        print("\n=== JSON 输出 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
