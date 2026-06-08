import json
import os
import pandas as pd
from datetime import datetime, date
from copy import deepcopy

OPERATION_LOG_FILE = "operation_logs.json"
PEAK_WARNING_FILE = "peak_warnings.json"
ACCEPTANCE_SNAPSHOT_FILE = "acceptance_snapshots.json"


def _json_serializer(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    raise TypeError(f"Type {type(obj)} not serializable")


def _ensure_file(filepath):
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def _read_json(filepath):
    _ensure_file(filepath)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_serializer)


def log_subsidy_operation(operator, subsidy_data, context):
    log_entry = {
        "log_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "operation_type": "补贴策略",
        "operator": operator,
        "timestamp": datetime.now().isoformat(),
        "subsidy_details": subsidy_data,
        "business_context": {
            "district": context["district"],
            "weather": context["weather"],
            "time_slot": context["time_slot"],
            "is_peak": context["is_peak"],
            "weather_factor": context["weather_factor"]
        },
        "status": "已执行"
    }
    logs = _read_json(OPERATION_LOG_FILE)
    logs.insert(0, log_entry)
    _write_json(OPERATION_LOG_FILE, logs)
    return log_entry


def record_peak_warning_full(
    warning_info, context,
    warning_snapshot,
    post_resolution_snapshot=None,
    scenario_tag=None
):
    record = {
        "record_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "record_type": "峰值预警",
        "timestamp": datetime.now().isoformat(),
        "warning_level": warning_info["预警级别"],
        "warning_contents": warning_info["预警内容"],
        "supply_demand_ratio": warning_info["供需比"],
        "dimension_details": warning_info.get("维度检测详情", {}),
        "threshold_hits": warning_info.get("阈值命中详情", []),
        "business_context": {
            "district": context["district"],
            "time_slot": context["time_slot"],
            "weather": context["weather"],
            "is_peak": context["is_peak"],
            "weather_factor": context["weather_factor"],
            "selected_date": str(context.get("selected_date", "")),
            "responsible": context.get("current_responsible", "")
        },
        "warning_snapshot": warning_snapshot,
        "post_resolution_snapshot": post_resolution_snapshot,
        "scenario_tag": scenario_tag,
        "playback_ready": True,
        "has_comparison": post_resolution_snapshot is not None
    }
    records = _read_json(PEAK_WARNING_FILE)
    records.insert(0, record)
    _write_json(PEAK_WARNING_FILE, records)
    return record


def record_peak_warning(warning_info, context):
    record = {
        "record_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "record_type": "峰值预警",
        "timestamp": datetime.now().isoformat(),
        "warning_level": warning_info["预警级别"],
        "warning_contents": warning_info["预警内容"],
        "supply_demand_ratio": warning_info["供需比"],
        "business_context": context,
        "playback_ready": True
    }
    records = _read_json(PEAK_WARNING_FILE)
    records.insert(0, record)
    _write_json(PEAK_WARNING_FILE, records)
    return record


def query_peak_warnings(
    district=None,
    warning_level=None,
    start_time=None,
    end_time=None,
    scenario_tag=None,
    limit=100
):
    records = _read_json(PEAK_WARNING_FILE)
    results = []

    for r in records:
        if district:
            ctx = r.get("business_context", {})
            if ctx.get("district") != district:
                continue
        if warning_level:
            if r.get("warning_level") != warning_level:
                continue
        if start_time:
            if r.get("timestamp", "") < start_time:
                continue
        if end_time:
            if r.get("timestamp", "") > end_time:
                continue
        if scenario_tag:
            if r.get("scenario_tag") != scenario_tag:
                continue
        results.append(r)
        if len(results) >= limit:
            break

    return results


def get_peak_warning_by_id(record_id):
    records = _read_json(PEAK_WARNING_FILE)
    for r in records:
        if r.get("record_id") == record_id:
            return r
    return None


def save_acceptance_snapshot(snapshot_type, data, description=""):
    snapshot = {
        "snapshot_id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "snapshot_type": snapshot_type,
        "timestamp": datetime.now().isoformat(),
        "description": description,
        "data": data
    }
    snapshots = _read_json(ACCEPTANCE_SNAPSHOT_FILE)
    snapshots.insert(0, snapshot)
    _write_json(ACCEPTANCE_SNAPSHOT_FILE, snapshots)
    return snapshot


def get_operation_logs(limit=100):
    logs = _read_json(OPERATION_LOG_FILE)
    return logs[:limit]


def get_peak_warnings(limit=100):
    records = _read_json(PEAK_WARNING_FILE)
    return records[:limit]


def get_acceptance_snapshots(snapshot_type=None, limit=100):
    snapshots = _read_json(ACCEPTANCE_SNAPSHOT_FILE)
    if snapshot_type:
        snapshots = [s for s in snapshots if s["snapshot_type"] == snapshot_type]
    return snapshots[:limit]


def logs_to_dataframe(logs):
    if not logs:
        return pd.DataFrame()
    rows = []
    for log in logs:
        ctx = log.get("business_context", {})
        subsidy = log.get("subsidy_details", {})
        strategies = subsidy.get("补贴策略", [])
        rows.append({
            "日志ID": log["log_id"],
            "时间": log["timestamp"],
            "操作人": log["operator"],
            "商圈": ctx.get("district", ""),
            "时段": ctx.get("time_slot", ""),
            "天气": ctx.get("weather", ""),
            "预警级别": subsidy.get("预警级别", ""),
            "补贴策略数": len(strategies),
            "状态": log["status"]
        })
    return pd.DataFrame(rows)


def warnings_to_dataframe(warnings):
    if not warnings:
        return pd.DataFrame()
    rows = []
    for w in warnings:
        ctx = w.get("business_context", {})
        level_badge = {
            "严重": "🔴 严重",
            "警告": "🟡 警告",
            "正常": "🟢 正常"
        }
        hit_dims = []
        for hit in w.get("threshold_hits", []):
            if hit.get("hit_level") != "正常":
                hit_dims.append(hit["dimension"])
        rows.append({
            "记录ID": w["record_id"],
            "时间": w.get("timestamp", ""),
            "预警级别": level_badge.get(w.get("warning_level", ""), w.get("warning_level", "")),
            "预警等级原始": w.get("warning_level", ""),
            "商圈": ctx.get("district", ""),
            "时段": ctx.get("time_slot", ""),
            "天气": ctx.get("weather", ""),
            "是否高峰期": "是" if ctx.get("is_peak") else "否",
            "供需比": w.get("supply_demand_ratio", ""),
            "触发维度": "、".join(hit_dims) if hit_dims else "无",
            "可回放": "✅" if w.get("playback_ready") else "❌",
            "可对比": "✅" if w.get("has_comparison") else "❌",
            "场景标签": w.get("scenario_tag", ""),
            "预警内容摘要": "；".join(w.get("warning_contents", [])[:2])
        })
    return pd.DataFrame(rows)


def snapshots_to_dataframe(snapshots):
    if not snapshots:
        return pd.DataFrame()
    rows = []
    for s in snapshots:
        rows.append({
            "快照ID": s["snapshot_id"],
            "时间": s["timestamp"],
            "类型": s["snapshot_type"],
            "描述": s["description"]
        })
    return pd.DataFrame(rows)


def clear_all_warnings():
    _write_json(PEAK_WARNING_FILE, [])
    return True
