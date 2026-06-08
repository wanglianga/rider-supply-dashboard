import json
import os
import pandas as pd
from datetime import datetime, date

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
    """记录补贴策略操作日志"""
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


def record_peak_warning(warning_info, context):
    """记录峰值预警到最终记录"""
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


def save_acceptance_snapshot(snapshot_type, data, description=""):
    """保存验收快照：订单热区输入、超时率判定、峰值预警回看"""
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
    """获取操作日志"""
    logs = _read_json(OPERATION_LOG_FILE)
    return logs[:limit]


def get_peak_warnings(limit=100):
    """获取峰值预警记录"""
    records = _read_json(PEAK_WARNING_FILE)
    return records[:limit]


def get_acceptance_snapshots(snapshot_type=None, limit=100):
    """获取验收快照"""
    snapshots = _read_json(ACCEPTANCE_SNAPSHOT_FILE)
    if snapshot_type:
        snapshots = [s for s in snapshots if s["snapshot_type"] == snapshot_type]
    return snapshots[:limit]


def logs_to_dataframe(logs):
    """将操作日志转为DataFrame便于展示"""
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
    """将峰值预警记录转为DataFrame"""
    if not warnings:
        return pd.DataFrame()
    rows = []
    for w in warnings:
        ctx = w.get("business_context", {})
        rows.append({
            "记录ID": w["record_id"],
            "时间": w["timestamp"],
            "预警级别": w["warning_level"],
            "商圈": ctx.get("district", ""),
            "时段": ctx.get("time_slot", ""),
            "天气": ctx.get("weather", ""),
            "供需比": w.get("supply_demand_ratio", ""),
            "预警数": len(w.get("warning_contents", [])),
            "可回放": w.get("playback_ready", False)
        })
    return pd.DataFrame(rows)


def snapshots_to_dataframe(snapshots):
    """将验收快照转为DataFrame"""
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
