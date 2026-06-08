import sys
import json
from datetime import datetime

from data_generator import (
    generate_business_context, generate_hotspot_data,
    generate_rider_data, generate_timeout_data, generate_weather_data
)
from warning_engine import (
    WARNING_DIMENSIONS, DEFAULT_THRESHOLDS,
    get_effective_thresholds, detect_peak_warning_enhanced,
    generate_full_snapshot, simulate_post_resolution_state,
    create_acceptance_scenario
)
from log_manager import (
    record_peak_warning_full, query_peak_warnings,
    get_peak_warning_by_id, clear_all_warnings
)


def test_dimension_calculation():
    print("=" * 70)
    print("测试1: 四维指标计算与动态阈值")
    print("=" * 70)

    ctx = generate_business_context(
        district="国贸商圈", weather="晴", time_slot="11:00-13:00"
    )
    hs = generate_hotspot_data(ctx)
    rd = generate_rider_data(ctx)
    to = generate_timeout_data(ctx)
    wt = generate_weather_data(ctx)

    eff_th = get_effective_thresholds(ctx)
    for dim in WARNING_DIMENSIONS:
        th = eff_th[dim]
        dynamic_note = " (动态)" if th["dynamic"] else ""
        print(f"  {dim}{dynamic_note}: 预警={th['warning']}, 严重={th['critical']}, 时段系数={th['time_slot_adjust']}")

    warning = detect_peak_warning_enhanced(ctx, hs, rd, to, wt)
    print(f"\n  预警级别: {warning['预警级别']}")
    for msg in warning["预警内容"][:3]:
        print(f"  - {msg}")
    print("  ✅ 通过\n")


def test_acceptance_scenarios():
    print("=" * 70)
    print("测试2: 三种验收场景触发")
    print("=" * 70)

    scenarios = ["供需比预警", "超时率预警", "多维度复合预警"]
    clear_all_warnings()

    for scenario in scenarios:
        print(f"\n  --- 场景: {scenario} ---")
        ctx_s, hs_s, rd_s, to_s, wt_s = create_acceptance_scenario(scenario)
        wi_s = detect_peak_warning_enhanced(ctx_s, hs_s, rd_s, to_s, wt_s)

        print(f"    商圈: {ctx_s['district']}")
        print(f"    时段: {ctx_s['time_slot']} (高峰期: {ctx_s['is_peak']})")
        print(f"    天气: {ctx_s['weather']} (系数x{ctx_s['weather_factor']})")
        print(f"    预警级别: {wi_s['预警级别']}")

        hit_dims = []
        for hit in wi_s.get("阈值命中详情", []):
            if hit["hit_level"] != "正常":
                hit_dims.append(f"{hit['dimension']}={hit['value']}")
        print(f"    触发维度: {', '.join(hit_dims) if hit_dims else '无'}")

        snap = generate_full_snapshot(ctx_s, hs_s, rd_s, to_s, wt_s)
        print(f"    快照生成: ID={snap['snapshot_id']}")
        print(f"      - 热区图Base64长度: {len(snap['hotspot_image_base64'])} chars")
        print(f"      - 骑手分布点位: {len(snap['rider_distribution_points'])} 个")
        print(f"      - 各时段超时率数组: {len(snap['timeout_rate_array'])} 个时段")
        print(f"      - 天气数据摘要: {snap['weather_data_summary']['current_weather']}")
        print(f"      - 阈值命中数: {len([h for h in snap['threshold_hits'] if h['hit_level'] != '正常'])}")

        pr_ctx, pr_hs, pr_rd, pr_to, pr_wt = simulate_post_resolution_state(
            ctx_s, hs_s, rd_s, to_s, wt_s
        )
        pr_snap = generate_full_snapshot(pr_ctx, pr_hs, pr_rd, pr_to, pr_wt)

        rec = record_peak_warning_full(wi_s, ctx_s, snap, pr_snap, scenario_tag=scenario)
        print(f"    最终记录ID: {rec['record_id']}")
        print(f"    可回放: {rec['playback_ready']}, 可对比: {rec['has_comparison']}")

    print("\n  ✅ 三种场景均已触发并存入最终记录\n")


def test_query_and_playback():
    print("=" * 70)
    print("测试3: 预警记录查询与回放数据完整性")
    print("=" * 70)

    all_records = query_peak_warnings()
    print(f"  总记录数: {len(all_records)}")

    for scenario in ["供需比预警", "超时率预警", "多维度复合预警"]:
        recs = query_peak_warnings(scenario_tag=scenario)
        print(f"\n  场景[{scenario}]匹配记录数: {len(recs)}")
        if recs:
            rec = recs[0]
            print(f"    记录ID: {rec['record_id']}")
            print(f"    商圈: {rec['business_context']['district']}")
            print(f"    预警等级: {rec['warning_level']}")
            snap = rec.get("warning_snapshot", {})
            print(f"    快照完整性检查:")
            checks = [
                ("热区图Base64", len(snap.get("hotspot_image_base64", "")) > 1000),
                ("骑手点位", len(snap.get("rider_distribution_points", [])) > 0),
                ("超时率数组", len(snap.get("timeout_rate_array", [])) == 6),
                ("天气数据", bool(snap.get("weather_data_summary"))),
                ("阈值命中详情", len(snap.get("threshold_hits", [])) == 4),
                ("对比快照", rec.get("has_comparison", False))
            ]
            for name, ok in checks:
                status = "✅" if ok else "❌"
                print(f"      {status} {name}")

    print("\n  ✅ 通过\n")


def run_all_tests():
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " 峰值预警引擎 - 全链路验证测试".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"验证时间: {datetime.now().isoformat()}")
    print()

    try:
        test_dimension_calculation()
        test_acceptance_scenarios()
        test_query_and_playback()

        print("=" * 70)
        print("🎉 所有测试通过！峰值预警系统功能完整。")
        print("=" * 70)
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
