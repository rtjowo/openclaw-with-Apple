#!/usr/bin/env python3
"""Apple Health 数据分析工具。

读取 iOS 快捷指令每日导出到 iCloud Drive 的健康数据文件，
分析用户的健康状态、压力状态、睡眠质量，并给出建议。

数据文件路径: ~/Library/Mobile Documents/com~apple~CloudDocs/Shortcuts/Health/
文件格式: health_YYYY-MM-DD.json 或 health_YYYY-MM-DD.txt

用法：
  python health_tool.py analyze  <file_or_dir>           # 分析单日或多日数据并给出建议
  python health_tool.py report   <dir> [--days 7]        # 多日趋势报告
  python health_tool.py today    [dir]                    # 分析今天的数据
"""

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# iCloud Drive 默认路径
# ---------------------------------------------------------------------------

DEFAULT_HEALTH_DIR = os.path.expanduser(
    "~/Library/Mobile Documents/com~apple~CloudDocs/Shortcuts/Health"
)

# ---------------------------------------------------------------------------
# 数据解析 — 兼容快捷指令生成的非标准 JSON
# ---------------------------------------------------------------------------

def fix_shortcut_json(raw_text):
    """修复快捷指令生成的非标准 JSON。

    快捷指令拼接的 JSON 常见问题：
    - 值里有多余空格: "v":72 " → "v":72
    - 中文全角括号: ］ → ]
    - 尾部逗号: ,] → ]
    - 数值后带引号: 72 " → 72
    - Windows 换行符: \r\n
    """
    text = raw_text
    # 统一换行符
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 全角 → 半角
    text = text.replace("，", ",").replace("：", ":").replace("［", "[").replace("］", "]")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    # 修复 "v":72 " 这种模式（JSON key 冒号后紧跟数字 + 空格 + 多余引号）
    # 需要确保冒号前面紧跟引号（即 JSON 的 "key":value 形式）
    text = re.sub(r'":(\d+\.?\d*) +"(\s*[,}\]])', r'":\1\2', text)
    # 修复 "t":"08:32 " 这种模式（字符串值尾部空格在闭合引号前）
    text = re.sub(r'"([^"]*?) +"(\s*[,}\]])', r'"\1"\2', text)
    # 修复尾部逗号
    text = re.sub(r',\s*([}\]])', r'\1', text)
    return text


def load_health_file(filepath):
    """加载单个健康数据文件（.json 或 .txt）。"""
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"文件不存在: {filepath}", file=sys.stderr)
        return None

    raw = filepath.read_text(encoding="utf-8")
    fixed = fix_shortcut_json(raw)

    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败 ({filepath.name}): {e}", file=sys.stderr)
        print(f"  修复后内容前 200 字符: {fixed[:200]}", file=sys.stderr)
        return None


def load_health_dir(dirpath, days=None):
    """加载目录中的所有健康数据文件。"""
    dirpath = Path(dirpath)
    if not dirpath.exists():
        print(f"目录不存在: {dirpath}", file=sys.stderr)
        return []

    cutoff = None
    if days:
        cutoff = datetime.now() - timedelta(days=days)

    results = []
    for f in sorted(dirpath.glob("health_*")):
        if f.suffix not in (".json", ".txt"):
            continue
        try:
            date_str = re.search(r"health_(\d{4}-\d{2}-\d{2})", f.stem)
            if not date_str:
                continue
            dt = datetime.strptime(date_str.group(1), "%Y-%m-%d")
            if cutoff and dt < cutoff:
                continue
        except ValueError:
            continue

        data = load_health_file(f)
        if data:
            data["_file"] = f.name
            results.append(data)

    return sorted(results, key=lambda x: x.get("date", ""))


# ---------------------------------------------------------------------------
# 心率分析
# ---------------------------------------------------------------------------

def analyze_heart_rate(hr_data):
    """深度分析心率数据。

    hr_data: list of {"t": "HH:mm", "v": float}

    返回：基础统计 + 心率变异性估算 + 突变事件 + 自主神经评估
    """
    if not hr_data or not isinstance(hr_data, list):
        return None

    # 解析带时间的心率点
    timed_values = []
    for item in hr_data:
        try:
            t = item.get("t", "").strip()
            v = float(item.get("v", 0))
            if v <= 0:
                continue
            parts = t.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            total_min = hour * 60 + minute
            timed_values.append({"min": total_min, "hour": hour, "v": v})
        except (TypeError, ValueError, IndexError):
            continue

    if not timed_values:
        return None

    timed_values.sort(key=lambda x: x["min"])
    values = [tv["v"] for tv in timed_values]

    avg_hr = sum(values) / len(values)
    max_hr = max(values)
    min_hr = min(values)
    hr_range = max_hr - min_hr

    # 静息心率：最低 20% 的平均值
    resting_candidates = sorted(values)[:max(1, len(values) // 5)]
    resting_hr = sum(resting_candidates) / len(resting_candidates)

    # 标准差 — 心率波动幅度
    variance = sum((v - avg_hr) ** 2 for v in values) / len(values)
    std_dev = variance ** 0.5

    # --------------- HRV 估算（RMSSD 近似）---------------
    successive_diffs = []
    for i in range(1, len(timed_values)):
        time_gap = timed_values[i]["min"] - timed_values[i - 1]["min"]
        if 0 < time_gap <= 10:
            diff = timed_values[i]["v"] - timed_values[i - 1]["v"]
            successive_diffs.append(diff ** 2)
    rmssd_est = (sum(successive_diffs) / len(successive_diffs)) ** 0.5 if successive_diffs else None

    # --------------- 心率突变事件检测 ---------------
    spike_events = []
    for i in range(1, len(timed_values)):
        time_gap = timed_values[i]["min"] - timed_values[i - 1]["min"]
        if time_gap > 30:
            continue
        delta = timed_values[i]["v"] - timed_values[i - 1]["v"]
        if abs(delta) >= 25:
            h, m = divmod(timed_values[i]["min"], 60)
            spike_events.append({
                "time": f"{h:02d}:{m:02d}",
                "from": round(timed_values[i - 1]["v"]),
                "to": round(timed_values[i]["v"]),
                "delta": round(delta),
            })

    # --------------- 按时段分析 ---------------
    period_def = [
        ("夜间(0-6)", 0, 6), ("上午(6-12)", 6, 12),
        ("下午(12-18)", 12, 18), ("晚间(18-24)", 18, 24),
    ]
    periods = {}
    for name, h_start, h_end in period_def:
        pv = [tv["v"] for tv in timed_values if h_start <= tv["hour"] < h_end]
        if pv:
            periods[name] = {
                "avg": round(sum(pv) / len(pv), 1),
                "min": round(min(pv), 1),
                "max": round(max(pv), 1),
                "count": len(pv),
            }
        else:
            periods[name] = None

    # --------------- 夜间静息心率（睡眠中的真实静息）---------------
    night_vals = [tv["v"] for tv in timed_values if 0 <= tv["hour"] < 6]
    night_resting = None
    if len(night_vals) >= 3:
        sorted_night = sorted(night_vals)
        bottom = sorted_night[:max(1, len(sorted_night) // 3)]
        night_resting = round(sum(bottom) / len(bottom), 1)

    # --------------- 自主神经系统状态评估 ---------------
    ans_state = None
    if rmssd_est is not None:
        if rmssd_est < 5:
            ans_state = "交感神经高度激活（高压/焦虑状态）"
        elif rmssd_est < 10:
            ans_state = "交感神经轻度优势（一般压力状态）"
        elif rmssd_est < 18:
            ans_state = "自主神经平衡（正常状态）"
        else:
            ans_state = "副交感神经优势（放松/恢复良好）"

    # --------------- 心率下降/恢复速度 ---------------
    # 检测运动后心率恢复：找到 max_hr 点后 5 分钟的心率
    max_idx = values.index(max_hr)
    recovery_1min = None
    if max_idx < len(timed_values) - 1:
        for j in range(max_idx + 1, len(timed_values)):
            gap = timed_values[j]["min"] - timed_values[max_idx]["min"]
            if 1 <= gap <= 3:
                recovery_1min = round(max_hr - timed_values[j]["v"])
                break

    return {
        "count": len(values),
        "avg": round(avg_hr, 1),
        "max": round(max_hr, 1),
        "min": round(min_hr, 1),
        "range": round(hr_range, 1),
        "std_dev": round(std_dev, 1),
        "resting_est": round(resting_hr, 1),
        "night_resting": night_resting,
        "rmssd_est": round(rmssd_est, 1) if rmssd_est is not None else None,
        "ans_state": ans_state,
        "spike_events": spike_events,
        "periods": periods,
        "recovery_1min": recovery_1min,
        "timed_values": timed_values,
    }


# ---------------------------------------------------------------------------
# 睡眠分析
# ---------------------------------------------------------------------------

def analyze_sleep(sleep_data):
    """深度分析睡眠数据。

    sleep_data: list of {"start": "HH:mm", "end": "HH:mm", "type": "Core|Deep|REM|Awake"}

    返回：基础统计 + 睡眠周期分析 + 碎片化指数 + 睡眠效率 + 结构评估
    """
    if not sleep_data or not isinstance(sleep_data, list):
        return None

    type_minutes = defaultdict(float)
    total_minutes = 0
    stages = []

    for item in sleep_data:
        try:
            start_str = item.get("start", "").strip()
            end_str = item.get("end", "").strip()
            sleep_type = item.get("type", "").strip()

            sh, sm = map(int, start_str.split(":"))
            eh, em = map(int, end_str.split(":"))

            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            if end_min < start_min:
                end_min += 24 * 60

            duration = end_min - start_min
            if duration <= 0:
                continue

            type_minutes[sleep_type] += duration
            total_minutes += duration
            stages.append({
                "type": sleep_type,
                "start": start_str,
                "end": end_str,
                "start_min": start_min,
                "end_min": end_min if end_min < 24 * 60 else end_min,
                "minutes": duration,
            })
        except (TypeError, ValueError):
            continue

    if total_minutes == 0:
        return None

    # Awake 不算入实际睡眠
    awake_min = type_minutes.get("Awake", 0)
    actual_sleep_min = total_minutes - awake_min

    sleep_start = stages[0]["start"] if stages else "?"
    sleep_end = stages[-1]["end"] if stages else "?"

    deep_pct = round(type_minutes.get("Deep", 0) / actual_sleep_min * 100, 1) if actual_sleep_min > 0 else 0
    rem_pct = round(type_minutes.get("REM", 0) / actual_sleep_min * 100, 1) if actual_sleep_min > 0 else 0
    core_pct = round(type_minutes.get("Core", 0) / actual_sleep_min * 100, 1) if actual_sleep_min > 0 else 0

    # --------------- 睡眠效率 ---------------
    sleep_efficiency = round(actual_sleep_min / total_minutes * 100, 1) if total_minutes > 0 else 0

    # --------------- 入睡时间评估 ---------------
    first_stage = stages[0] if stages else None
    bedtime_hour = None
    if first_stage:
        h = first_stage["start_min"] // 60
        if h >= 24:
            h -= 24
        bedtime_hour = h + (first_stage["start_min"] % 60) / 60.0

    # --------------- 睡眠碎片化指数 ---------------
    transitions = 0
    awake_episodes = 0
    for i in range(1, len(stages)):
        if stages[i]["type"] != stages[i - 1]["type"]:
            transitions += 1
        if stages[i]["type"] == "Awake":
            awake_episodes += 1
    fragmentation_idx = round(transitions / (actual_sleep_min / 60), 1) if actual_sleep_min > 0 else 0

    # --------------- 睡眠周期检测 ---------------
    cycle_count = 0
    found_deep = False
    for s in stages:
        if s["type"] == "Deep":
            found_deep = True
        elif s["type"] == "REM" and found_deep:
            cycle_count += 1
            found_deep = False

    # --------------- 前半夜 vs 后半夜结构 ---------------
    if len(stages) >= 2:
        midpoint_min = stages[0]["start_min"] + total_minutes // 2
        first_half = {"Deep": 0, "REM": 0, "Core": 0}
        second_half = {"Deep": 0, "REM": 0, "Core": 0}
        for s in stages:
            if s["type"] == "Awake":
                continue
            bucket = first_half if s["start_min"] < midpoint_min else second_half
            if s["type"] in bucket:
                bucket[s["type"]] += s["minutes"]
        first_half_total = sum(first_half.values()) or 1
        second_half_total = sum(second_half.values()) or 1
    else:
        first_half = second_half = None
        first_half_total = second_half_total = 1

    # --------------- 最长连续睡眠段 ---------------
    max_continuous = 0
    current_run = 0
    for s in stages:
        if s["type"] != "Awake":
            current_run += s["minutes"]
            max_continuous = max(max_continuous, current_run)
        else:
            current_run = 0

    # --------------- 入睡潜伏期（第一段若是 Core 且很短，可能是入睡前的辗转）---------------
    sleep_latency_min = 0
    if stages and stages[0]["type"] == "Awake":
        sleep_latency_min = stages[0]["minutes"]

    # --------------- 各阶段详细时间线 ---------------
    stage_timeline = []
    for s in stages:
        stage_timeline.append({
            "type": s["type"],
            "start": s["start"],
            "end": s["end"],
            "minutes": s["minutes"],
        })

    result = {
        "total_hours": round(total_minutes / 60, 1),
        "actual_sleep_hours": round(actual_sleep_min / 60, 1),
        "sleep_start": sleep_start,
        "sleep_end": sleep_end,
        "bedtime_hour": round(bedtime_hour, 1) if bedtime_hour is not None else None,
        "stages": {k: round(v / 60, 1) for k, v in type_minutes.items()},
        "stage_count": len(stages),
        "deep_pct": deep_pct,
        "rem_pct": rem_pct,
        "core_pct": core_pct,
        "sleep_efficiency": sleep_efficiency,
        "fragmentation_idx": fragmentation_idx,
        "transitions": transitions,
        "awake_episodes": awake_episodes,
        "cycle_count": cycle_count,
        "max_continuous_min": max_continuous,
        "sleep_latency_min": sleep_latency_min,
        "stage_timeline": stage_timeline,
    }

    if first_half is not None:
        result["first_half"] = {
            "deep_pct": round(first_half["Deep"] / first_half_total * 100, 1),
            "rem_pct": round(first_half["REM"] / first_half_total * 100, 1),
        }
        result["second_half"] = {
            "deep_pct": round(second_half["Deep"] / second_half_total * 100, 1),
            "rem_pct": round(second_half["REM"] / second_half_total * 100, 1),
        }

    return result


def type_minutes_total(sleep_analysis, sleep_type):
    """辅助：获取某种睡眠阶段的总小时数。"""
    return sleep_analysis.get("stages", {}).get(sleep_type, 0)


# ---------------------------------------------------------------------------
# 综合健康评估与建议（深度版）
# ---------------------------------------------------------------------------

def _build_hr_timeline_narrative(hr_analysis, sleep_analysis):
    """构建心率时间线叙事 — 用你的实际数据讲述身体一天的故事。"""
    narrative = []
    if not hr_analysis:
        return narrative

    periods = hr_analysis["periods"]
    spikes = hr_analysis.get("spike_events", [])

    night = periods.get("夜间(0-6)")
    morning = periods.get("上午(6-12)")
    afternoon = periods.get("下午(12-18)")
    evening = periods.get("晚间(18-24)")

    story_parts = []

    # --- 睡眠时段的心率故事 ---
    if night:
        night_resting = hr_analysis.get("night_resting")
        if night_resting and night_resting < 60:
            story_parts.append(
                "凌晨时段身体进入深度恢复模式，心率降至 {:.0f} bpm，"
                "副交感神经正常接管了夜间修复工作。".format(night_resting)
            )
        elif night_resting and night_resting >= 70:
            story_parts.append(
                "凌晨 0-6 点心率仍维持在 {:.0f} bpm 的较高水平，"
                "身体在睡眠中没有充分「降档」——可能是入睡前摄入了咖啡因/酒精，"
                "或者精神压力让交感神经在夜间仍然活跃。".format(night_resting)
            )
        elif night_resting:
            story_parts.append(
                "夜间静息心率 {:.0f} bpm，处于正常范围。".format(night_resting)
            )

        if night["max"] - night["min"] > 30:
            story_parts.append(
                "夜间心率波动范围大（{:.0f}-{:.0f} bpm），可能存在夜间醒来、"
                "翻身频繁或做梦强烈的情况。".format(night["min"], night["max"])
            )

    # --- 清晨唤醒 ---
    if morning and night and night["avg"] > 0:
        wake_jump = morning["avg"] - night["avg"]
        if wake_jump > 20:
            story_parts.append(
                "醒来后心率从夜间均值 {:.0f} 跳升到上午均值 {:.0f} bpm"
                "（+{:.0f}），晨起交感神经快速激活。如果伴有"
                "起床后心悸或头晕，建议起床时先在床上坐 30 秒再站立。".format(
                    night["avg"], morning["avg"], wake_jump
                )
            )

    # --- 日间活动高峰解读 ---
    for sp in spikes[:3]:
        h_str, m_str = sp["time"].split(":")
        hour = int(h_str)
        if sp["delta"] > 0:
            if 6 <= hour < 12:
                context = "上午"
            elif 12 <= hour < 14:
                context = "午餐前后"
            elif 14 <= hour < 18:
                context = "下午"
            else:
                context = "晚间"
            story_parts.append(
                "{} {} 心率从 {} 飙升至 {} bpm（+{} bpm）—— "
                "这个时间点你在做什么？如果是运动/爬楼梯属正常反应；"
                "如果是坐着工作时突然飙升，可能是情绪波动或咖啡因反应。".format(
                    context, sp["time"], sp["from"], sp["to"], sp["delta"]
                )
            )

    # --- 下午到晚间的恢复 ---
    if afternoon and evening:
        if evening["avg"] > afternoon["avg"] + 5:
            story_parts.append(
                "晚间心率（{:.0f}）反而高于下午（{:.0f}），"
                "正常应随一天结束而下降。可能是晚餐过饱、晚间运动、"
                "或睡前焦虑导致。".format(evening["avg"], afternoon["avg"])
            )
        elif evening["avg"] < 65 and afternoon["avg"] > 75:
            story_parts.append(
                "下午 {:.0f} bpm → 晚间 {:.0f} bpm，"
                "心率下降曲线良好，身体在为入睡做准备。".format(
                    afternoon["avg"], evening["avg"]
                )
            )

    if story_parts:
        narrative.append("你的一天（心率视角）：")
        for part in story_parts:
            narrative.append(part)

    return narrative


def _build_sleep_architecture_narrative(sleep_analysis):
    """构建睡眠架构深度叙事。"""
    narrative = []
    if not sleep_analysis:
        return narrative

    deep_pct = sleep_analysis["deep_pct"]
    rem_pct = sleep_analysis["rem_pct"]
    core_pct = sleep_analysis["core_pct"]
    efficiency = sleep_analysis["sleep_efficiency"]
    first_half = sleep_analysis.get("first_half")
    second_half = sleep_analysis.get("second_half")
    max_cont = sleep_analysis["max_continuous_min"]

    # 睡眠架构整体画像
    if deep_pct >= 20 and rem_pct >= 20 and efficiency >= 90:
        narrative.append(
            "睡眠架构接近「教科书级」：深度 {:.1f}%、REM {:.1f}%、效率 {:.1f}%。"
            "大脑和身体都获得了充分修复。".format(deep_pct, rem_pct, efficiency)
        )
    elif deep_pct < 13 and rem_pct < 18:
        narrative.append(
            "深度睡眠（{:.1f}%）和 REM（{:.1f}%）双低，浅睡（Core）占比 {:.1f}% 过大。"
            "你的睡眠大部分时间停留在「最没用的」浅睡阶段——"
            "身体没有真正修复，大脑也没有完成记忆整理和情绪清理。"
            "这种模式下即使睡了 8 小时也会觉得没休息好。".format(deep_pct, rem_pct, core_pct)
        )
    elif deep_pct < 13:
        narrative.append(
            "深度睡眠不足（{:.1f}%），但 REM 尚可（{:.1f}%）。"
            "身体的物理修复（肌肉恢复、免疫调节、生长激素分泌）受限，"
            "但大脑的情绪处理和记忆巩固基本完成。"
            "你可能会感觉身体疲惫但头脑还算清醒。".format(deep_pct, rem_pct)
        )
    elif rem_pct < 18:
        narrative.append(
            "REM 偏低（{:.1f}%），深度睡眠尚可（{:.1f}%）。"
            "身体修复完成但大脑的「情绪垃圾回收」不充分。"
            "你可能觉得身体恢复了，但情绪容易波动、注意力不易集中。".format(rem_pct, deep_pct)
        )

    # 前后半夜结构意义
    if first_half and second_half:
        if first_half["deep_pct"] > 25:
            narrative.append(
                "前半夜深度睡眠集中（{:.1f}%），符合正常的"
                "「先修复身体、后整理大脑」节律。"
                "前半夜是生长激素分泌的黄金期。".format(first_half["deep_pct"])
            )
        elif first_half["deep_pct"] < 10 and deep_pct > 0:
            narrative.append(
                "前半夜深度睡眠极少（{:.1f}%），深度睡眠被推迟到后半夜。"
                "这打乱了正常的「先深后浅」节律，可能是入睡时交感神经仍然活跃，"
                "身体需要更长时间才能进入深度修复。".format(first_half["deep_pct"])
            )
        if second_half["rem_pct"] > 30:
            narrative.append(
                "后半夜 REM 丰富（{:.1f}%），大脑在这段时间完成了大量"
                "情绪处理和创造性思维整合。这对学习和情绪健康非常有益。".format(
                    second_half["rem_pct"]
                )
            )

    # 最长连续睡眠段
    if max_cont >= 90:
        narrative.append(
            "最长连续睡眠 {} 分钟，达到完整周期（90 分钟）标准，"
            "大脑能完成浅睡→深睡→REM 的完整修复循环。".format(max_cont)
        )
    elif max_cont >= 60 and max_cont < 90:
        narrative.append(
            "最长连续睡眠 {} 分钟，差一点就能完成完整的 90 分钟周期。"
            "频繁中断导致深度睡眠和 REM 都无法充分展开。".format(max_cont)
        )
    elif max_cont > 0:
        narrative.append(
            "最长连续睡眠仅 {} 分钟，严重碎片化。"
            "无法完成任何完整的睡眠周期，恢复效果大打折扣。".format(max_cont)
        )

    return narrative


def _generate_action_plan(data, hr_analysis, sleep_analysis):
    """生成带时间表的个性化行动方案 — 告诉用户今天具体做什么。"""
    actions = []

    steps = data.get("steps", 0) if isinstance(data.get("steps"), (int, float)) else 0
    energy = data.get("active_energy_kcal", 0) if isinstance(data.get("active_energy_kcal"), (int, float)) else 0

    # 收集今日关键问题
    issues = []
    if sleep_analysis:
        actual = sleep_analysis["actual_sleep_hours"]
        bedtime_h = sleep_analysis.get("bedtime_hour")
        deep_pct = sleep_analysis["deep_pct"]
        efficiency = sleep_analysis["sleep_efficiency"]
        if actual < 6.5:
            issues.append("sleep_deficit")
        if bedtime_h is not None and bedtime_h >= 2 and bedtime_h < 12:
            issues.append("late_sleep")
        if deep_pct < 13:
            issues.append("low_deep")
        if efficiency < 85:
            issues.append("low_efficiency")

    if hr_analysis:
        rmssd = hr_analysis.get("rmssd_est")
        if rmssd and rmssd < 8:
            issues.append("low_hrv")
        night_resting = hr_analysis.get("night_resting") or hr_analysis["resting_est"]
        if night_resting > 70:
            issues.append("high_resting_hr")

    if steps < 4000:
        issues.append("low_activity")

    if not issues:
        actions.append(
            "各项指标正常。保持现有的生活节奏即可。"
            "如果想进一步提升，建议在下午安排 30 分钟中等强度运动（快走/游泳），"
            "这是提升 HRV 和深度睡眠最有效的单一干预。"
        )
        return actions

    # 根据问题组合生成具体方案
    if "sleep_deficit" in issues or "late_sleep" in issues:
        target_bedtime = "23:00"
        if sleep_analysis and sleep_analysis.get("bedtime_hour"):
            current_h = sleep_analysis["bedtime_hour"]
            if current_h >= 2:
                target_h = current_h - 0.5
                if target_h >= 2:
                    th = int(target_h)
                    tm = int((target_h - th) * 60)
                    target_bedtime = f"{th:02d}:{tm:02d}（比昨晚提前 30 分钟）"
                else:
                    target_bedtime = "01:30（逐步提前，一周内目标 23:30）"
        actions.append(
            "【今晚目标入睡时间：{}】\n"
            "  · 入睡前 90 分钟：停止高强度脑力工作，调暗室内灯光\n"
            "  · 入睡前 60 分钟：放下手机和电脑（蓝光抑制褪黑素分泌）\n"
            "  · 入睡前 30 分钟：做 5-10 分钟渐进式肌肉放松或腹式呼吸\n"
            "  · 卧室温度控制在 18-20°C，这是深度睡眠的最佳温度窗口".format(target_bedtime)
        )

    if "low_hrv" in issues:
        actions.append(
            "【自主神经调节 — 本周每天执行】\n"
            "  · 上午 10:00：4-7-8 呼吸法 × 4 轮（吸 4s→屏 7s→呼 8s），约 3 分钟\n"
            "  · 下午 15:00：重复一次 4-7-8 呼吸法\n"
            "  · 这是目前证据最充分的提升 HRV 干预手段，2-4 周可见显著变化\n"
            "  · 今天避免高强度运动——HRV 低时高强度训练会加重自主神经失衡"
        )

    if "low_activity" in issues:
        actions.append(
            "【增加活动量 — 从今天开始】\n"
            "  · 午餐后散步 15 分钟（即使只是在办公室楼下走走）\n"
            "  · 每工作 50 分钟，起身走动 3 分钟（设个闹钟）\n"
            "  · 晚餐后 30 分钟散步（同时促进消化和改善当晚深度睡眠）\n"
            "  · 目标：本周日均步数提升到 {} 步以上".format(
                max(5000, int(steps) + 2000)
            )
        )

    if "low_deep" in issues and "low_activity" not in issues:
        actions.append(
            "【提升深度睡眠 — 针对性干预】\n"
            "  · 下午 14:00-17:00 安排 30 分钟中等强度有氧运动"
            "（研究显示下午运动对当晚深度睡眠提升效果最佳，可增加 25-30%）\n"
            "  · 睡前 2 小时不进食（胃肠活动会抑制深度睡眠）\n"
            "  · 如果有饮酒习惯，今晚尝试不喝——酒精是深度睡眠的头号杀手，"
            "即使少量也会导致深度睡眠占比下降 20-40%"
        )

    if "high_resting_hr" in issues and "low_hrv" not in issues:
        actions.append(
            "【降低静息心率 — 中期计划】\n"
            "  · 每周 3-4 次、每次 30 分钟中等强度有氧运动（快走、游泳、骑车）\n"
            "  · 持续 4-8 周可使静息心率下降 5-10 bpm\n"
            "  · 减少咖啡因摄入（尤其下午 14:00 后），每日不超过 2 杯\n"
            "  · 如果连续一周夜间静息心率 > 70 bpm，建议排查甲亢或贫血"
        )

    return actions


def _compute_subscores(data, hr_analysis, sleep_analysis):
    """计算各维度子评分，返回 (subscores_dict, total_score, grade)。"""
    steps = data.get("steps", 0) if isinstance(data.get("steps"), (int, float)) else 0
    energy = data.get("active_energy_kcal", 0) if isinstance(data.get("active_energy_kcal"), (int, float)) else 0
    distance = data.get("distance_km", 0) if isinstance(data.get("distance_km"), (int, float)) else 0

    # --- 运动评分 (25分) ---
    activity_score = 25
    if steps < 2000:
        activity_score = 5
    elif steps < 4000:
        activity_score = 10
    elif steps < 6000:
        activity_score = 15
    elif steps < 8000:
        activity_score = 20

    if energy < 80:
        activity_score = max(0, activity_score - 5)
    elif energy > 300:
        activity_score = min(25, activity_score + 3)

    # --- 心血管评分 (25分) ---
    cardio_score = 25
    if hr_analysis:
        resting = hr_analysis.get("night_resting") or hr_analysis["resting_est"]
        if resting > 80:
            cardio_score -= 12
        elif resting > 75:
            cardio_score -= 8
        elif resting > 70:
            cardio_score -= 4
        elif resting < 50:
            cardio_score -= 5

        rmssd = hr_analysis.get("rmssd_est")
        if rmssd is not None:
            if rmssd < 5:
                cardio_score -= 10
            elif rmssd < 8:
                cardio_score -= 6
            elif rmssd < 12:
                cardio_score -= 3
            elif rmssd > 20:
                cardio_score = min(25, cardio_score + 2)

        if hr_analysis["range"] > 90:
            cardio_score -= 2

        spikes = hr_analysis.get("spike_events", [])
        if len(spikes) > 5:
            cardio_score -= 3
    else:
        cardio_score = 15  # 没有数据给一个中间值

    cardio_score = max(0, min(25, cardio_score))

    # --- 睡眠时长评分 (25分) ---
    sleep_score = 25
    if sleep_analysis:
        actual = sleep_analysis["actual_sleep_hours"]
        if actual < 4:
            sleep_score = 2
        elif actual < 5:
            sleep_score = 6
        elif actual < 6:
            sleep_score = 10
        elif actual < 6.5:
            sleep_score = 14
        elif actual < 7:
            sleep_score = 18
        elif actual > 9.5:
            sleep_score = 18

        if sleep_analysis.get("bedtime_hour") and 2 <= sleep_analysis["bedtime_hour"] < 12:
            sleep_score = max(0, sleep_score - 5)
    else:
        sleep_score = 15

    sleep_score = max(0, min(25, sleep_score))

    # --- 睡眠质量评分 (25分) ---
    quality_score = 25
    if sleep_analysis:
        deep_pct = sleep_analysis["deep_pct"]
        rem_pct = sleep_analysis["rem_pct"]
        efficiency = sleep_analysis["sleep_efficiency"]
        frag_idx = sleep_analysis["fragmentation_idx"]

        if deep_pct < 10:
            quality_score -= 8
        elif deep_pct < 15:
            quality_score -= 4

        if rem_pct < 15:
            quality_score -= 6
        elif rem_pct < 20:
            quality_score -= 3

        if efficiency < 80:
            quality_score -= 6
        elif efficiency < 85:
            quality_score -= 3

        if frag_idx > 6:
            quality_score -= 4
        elif frag_idx > 4:
            quality_score -= 2

        if sleep_analysis["awake_episodes"] >= 3:
            quality_score -= 3

        if sleep_analysis["max_continuous_min"] < 60:
            quality_score -= 4
    else:
        quality_score = 15

    quality_score = max(0, min(25, quality_score))

    total = activity_score + cardio_score + sleep_score + quality_score

    if total >= 85:
        grade = "优秀 — 身体恢复和活动量处于良好平衡"
    elif total >= 70:
        grade = "良好 — 整体状态不错，部分指标可优化"
    elif total >= 55:
        grade = "一般 — 存在明显健康负债，需要调整"
    elif total >= 40:
        grade = "偏差 — 多项指标预警，请优先保证休息"
    else:
        grade = "警告 — 身体发出强烈信号，立即调整作息"

    subscores = {
        "运动活力": (activity_score, 25),
        "心血管": (cardio_score, 25),
        "睡眠时长": (sleep_score, 25),
        "睡眠质量": (quality_score, 25),
    }

    return subscores, total, grade


def generate_health_advice(data, hr_analysis, sleep_analysis):
    """深层次健康分析与个性化建议。

    6 大板块：
    1. 运动与代谢分析
    2. 心血管与自主神经分析
    3. 心率时间线叙事（新增）
    4. 睡眠深度分析 + 睡眠架构叙事（新增）
    5. 交叉关联与风险信号
    6. 综合评定 + 个性化行动方案（新增）
    """
    sections = []

    steps = data.get("steps", 0) if isinstance(data.get("steps"), (int, float)) else 0
    energy = data.get("active_energy_kcal", 0) if isinstance(data.get("active_energy_kcal"), (int, float)) else 0
    distance = data.get("distance_km", 0) if isinstance(data.get("distance_km"), (int, float)) else 0

    # ==================== 1. 运动与代谢分析 ====================
    movement = []

    if steps > 0:
        if steps < 3000:
            movement.append(
                "今日仅 {} 步，属于久坐型活动量。长期日均不足 4000 步与心血管疾病风险"
                "升高 15-20% 相关（JAMA Internal Medicine, 2019）。即使无法大量运动，"
                "每小时起身走动 2-3 分钟也能显著降低久坐危害。".format(int(steps))
            )
        elif steps < 6000:
            movement.append(
                "今日 {} 步，略低于活跃标准。研究显示日均 7000-8000 步是全因死亡率"
                "显著下降的拐点。建议通过饭后散步、走路开会等方式自然增加步数。".format(int(steps))
            )
        elif steps < 10000:
            movement.append(
                "今日 {} 步，达到活跃水平，对心血管和代谢健康有积极意义。".format(int(steps))
            )
        else:
            movement.append(
                "今日 {} 步，运动量充足。注意高步数日补充水分和电解质。".format(int(steps))
            )

    if steps > 0 and energy > 0:
        cal_per_step = energy / steps
        if cal_per_step > 0.06:
            movement.append(
                "每步消耗约 {:.3f} kcal，高于平均水平（~0.04），说明今日活动中包含"
                "跑步、爬楼等较高强度运动，或携带了额外负重。".format(cal_per_step)
            )
        elif cal_per_step < 0.025 and steps > 5000:
            movement.append(
                "每步消耗仅 {:.3f} kcal，低于平均水平。步数虽不少，但活动强度偏低，"
                "多为平地慢走。建议穿插快走（步速 > 100 步/分钟）或爬坡，"
                "同样步数下可提升心肺效果 40-60%。".format(cal_per_step)
            )

    if steps > 0 and distance > 0:
        stride_m = distance * 1000 / steps
        if stride_m < 0.55:
            movement.append(
                "平均步幅约 {:.2f} 米，偏短（正常成人 0.65-0.80 米）。"
                "步幅缩短可能与疲劳、关节僵硬或缺乏拉伸有关。"
                "建议每天花 5 分钟做下肢拉伸，改善髋关节活动度。".format(stride_m)
            )
        elif stride_m > 0.85:
            movement.append(
                "平均步幅 {:.2f} 米，说明包含跑步段。".format(stride_m)
            )

    if energy > 0 and energy < 100:
        movement.append(
            "活动能量仅 {:.0f} kcal，接近基础代谢外的最低消耗。长期低活动量"
            "会导致胰岛素敏感性下降，建议至少达到 150 kcal/天以上。".format(energy)
        )

    if movement:
        sections.append(("🏃 运动与代谢", movement))

    # ==================== 2. 心血管与自主神经分析 ====================
    cardio = []

    if hr_analysis:
        resting = hr_analysis["resting_est"]
        night_resting = hr_analysis.get("night_resting")
        max_hr = hr_analysis["max"]
        min_hr = hr_analysis["min"]
        hr_range = hr_analysis["range"]
        std_dev = hr_analysis["std_dev"]
        rmssd = hr_analysis.get("rmssd_est")
        ans = hr_analysis.get("ans_state")
        recovery = hr_analysis.get("recovery_1min")

        if night_resting:
            cardio.append(
                "夜间深度静息心率 {:.0f} bpm（取凌晨 0-6 点最低 1/3 均值）。".format(night_resting)
            )
            if night_resting < 50:
                cardio.append(
                    "夜间静息心率极低，如果你不是长期耐力运动员，建议排查窦性心动过缓。"
                    "若伴有头晕、乏力，建议做心电图检查。"
                )
            elif night_resting > 70:
                cardio.append(
                    "夜间静息偏高（正常成人夜间应低于 65 bpm）。可能原因：睡前饮酒/咖啡、"
                    "高压力/焦虑状态、感染初期（体温每升高 1°C 心率约升高 8-10 bpm）、"
                    "或交感神经过度激活。建议连续观察 3-5 天。"
                )
            elif night_resting <= 65:
                cardio.append(
                    "夜间静息心率在健康范围内，心血管基础状态良好。"
                )
        else:
            if resting < 50:
                cardio.append(
                    "估算静息心率 {:.0f} bpm，偏低。如非运动员请关注。".format(resting)
                )
            elif resting >= 75:
                cardio.append(
                    "估算静息心率 {:.0f} bpm，偏高。长期 > 75 bpm 与心血管事件风险升高相关。"
                    "建议通过有氧运动（每周 150 分钟中等强度）逐步降低静息心率。".format(resting)
                )

        if rmssd is not None:
            cardio.append(
                "心率变异性 RMSSD ≈ {:.1f}（基于相邻测量差值估算）。{}".format(
                    rmssd, ans or ""
                )
            )
            if rmssd < 8:
                cardio.append(
                    "HRV 偏低提示交感神经主导，身体处于「战斗或逃跑」模式。"
                    "可能原因：工作压力大、睡眠不足、过度训练、情绪紧张。"
                    "建议：4-7-8 呼吸法（吸 4s→屏 7s→呼 8s）每天 5 分钟，"
                    "2-4 周内可显著提升 HRV。"
                )
            elif rmssd > 20:
                cardio.append(
                    "HRV 较高，说明副交感神经活跃、身体恢复能力强。"
                    "这是良好体能和低压力状态的标志。"
                )

        if hr_range > 80:
            cardio.append(
                "心率极差高达 {:.0f} bpm（{:.0f}→{:.0f}），日内波动剧烈。"
                "这通常意味着有高强度运动段或情绪波动大的时段。".format(hr_range, min_hr, max_hr)
            )

        # 心率恢复速度
        if recovery is not None and recovery > 0:
            if recovery >= 20:
                cardio.append(
                    "运动后心率恢复速度良好（峰值后 1-3 分钟下降 {} bpm），"
                    "说明心血管适应性和自主神经反射功能正常。".format(recovery)
                )
            elif recovery < 12:
                cardio.append(
                    "运动后心率恢复偏慢（峰值后仅下降 {} bpm），"
                    "正常应在 1 分钟内下降 > 12 bpm。恢复慢是心血管适应性差的标志，"
                    "建议增加有氧运动频率。".format(recovery)
                )

        # 心率突变事件
        spikes = hr_analysis.get("spike_events", [])
        if spikes:
            spike_lines = ["检测到 {} 次心率突变事件（相邻变化 ≥ 25 bpm）：".format(len(spikes))]
            for sp in spikes[:5]:
                direction = "飙升" if sp["delta"] > 0 else "骤降"
                spike_lines.append(
                    "  {} 心率{}：{} → {} bpm（Δ{:+d}）".format(
                        sp["time"], direction, sp["from"], sp["to"], sp["delta"]
                    )
                )
            cardio.append("\n".join(spike_lines))
            if len(spikes) > 3:
                cardio.append(
                    "频繁心率突变可能反映：间歇性高强度活动、惊吓/焦虑事件、"
                    "或体位性心动过速。如非运动导致，建议关注。"
                )

        # 时段交叉
        periods = hr_analysis["periods"]
        morning = periods.get("上午(6-12)")
        afternoon = periods.get("下午(12-18)")
        night = periods.get("夜间(0-6)")

        if morning and afternoon:
            daytime_avg = (morning["avg"] + afternoon["avg"]) / 2
            if daytime_avg > 85:
                cardio.append(
                    "白天平均心率 {:.0f} bpm，持续偏高。排除运动因素后，"
                    "这是慢性压力的典型心率表现。建议日间安排 2-3 次"
                    "5 分钟正念/深呼吸间隔。".format(daytime_avg)
                )
            elif night and night["avg"] > 0:
                day_night_diff = daytime_avg - night["avg"]
                if day_night_diff < 5:
                    cardio.append(
                        "昼夜心率差仅 {:.0f} bpm（白天 {:.0f}，夜间 {:.0f}），"
                        "正常人应有 10-20 bpm 差异。昼夜差异小可能提示：自主神经调节"
                        "功能下降、慢性疲劳、或夜间睡眠质量差。".format(
                            day_night_diff, daytime_avg, night["avg"]
                        )
                    )
                elif day_night_diff > 15:
                    cardio.append(
                        "昼夜心率差 {:.0f} bpm（白天 {:.0f}，夜间 {:.0f}），"
                        "节律正常，自主神经调节良好。".format(
                            day_night_diff, daytime_avg, night["avg"]
                        )
                    )

    if cardio:
        sections.append(("❤️ 心血管与自主神经", cardio))

    # ==================== 3. 心率时间线叙事 ====================
    timeline = _build_hr_timeline_narrative(hr_analysis, sleep_analysis)
    if timeline:
        sections.append(("📖 时间线叙事", timeline))

    # ==================== 4. 睡眠深度分析 ====================
    sleep_advice = []

    if sleep_analysis:
        actual = sleep_analysis["actual_sleep_hours"]
        total = sleep_analysis["total_hours"]
        deep_pct = sleep_analysis["deep_pct"]
        rem_pct = sleep_analysis["rem_pct"]
        efficiency = sleep_analysis["sleep_efficiency"]
        frag_idx = sleep_analysis["fragmentation_idx"]
        cycles = sleep_analysis["cycle_count"]
        bedtime_h = sleep_analysis.get("bedtime_hour")
        max_cont = sleep_analysis["max_continuous_min"]
        awake_eps = sleep_analysis["awake_episodes"]

        # 睡眠时长
        if actual < 5:
            sleep_advice.append(
                "实际睡眠仅 {:.1f} 小时，严重不足。单次不足 5 小时"
                "会导致次日认知下降约 30%，免疫功能下降 50%。"
                "睡眠债累积后补觉恢复效率仅约 30%。".format(actual)
            )
        elif actual < 6.5:
            sleep_advice.append(
                "实际睡眠 {:.1f} 小时，低于推荐 7-9 小时。"
                "长期 6 小时以下与肥胖风险 +23%、II 型糖尿病风险 +28% 相关。".format(actual)
            )
        elif actual >= 7 and actual <= 9:
            sleep_advice.append(
                "实际睡眠 {:.1f} 小时，时长合理。".format(actual)
            )
        elif actual > 9.5:
            sleep_advice.append(
                "实际睡眠 {:.1f} 小时，偏长。超过 9 小时反而与炎症标记物升高相关，"
                "可能是睡眠质量差（需更多时间才能恢复）的信号。".format(actual)
            )

        # 入睡时间
        if bedtime_h is not None:
            if bedtime_h >= 2 and bedtime_h < 12:
                sleep_advice.append(
                    "入睡时间为凌晨 {}。人体褪黑素分泌高峰在 21:00-23:00，"
                    "错过这个窗口入睡会导致深度睡眠占比下降、生长激素分泌减少。"
                    "建议每天提前 15 分钟入睡，用 2-3 周逐步调整。".format(
                        sleep_analysis["sleep_start"]
                    )
                )
            elif bedtime_h >= 1:
                sleep_advice.append(
                    "入睡时间 {}，偏晚。错过 23:00 前入睡窗口会影响前半夜"
                    "深度睡眠质量。".format(sleep_analysis["sleep_start"])
                )

        # 睡眠效率
        if efficiency < 85:
            awake_min = (total - actual) * 60
            sleep_advice.append(
                "睡眠效率 {:.1f}%（低于 85%）。"
                "你在床上有 {:.0f} 分钟处于清醒状态。"
                "建议限制在床上的非睡眠活动（不在床上刷手机/工作）。".format(
                    efficiency, awake_min
                )
            )

        # 碎片化
        if frag_idx > 5:
            sleep_advice.append(
                "睡眠碎片化指数 {:.1f}（阶段切换/小时），偏高。"
                "频繁切换导致恢复效率降低。可能原因：环境噪音、"
                "温度不适（最佳 18-20°C）、睡前蓝光、睡前 2 小时内剧烈运动。".format(frag_idx)
            )
        if awake_eps >= 3:
            sleep_advice.append(
                "夜间醒来 {} 次。频繁夜醒是睡眠质量差的核心指标，"
                "每次醒来后需 10-20 分钟才能重新进入深睡。".format(awake_eps)
            )

        # 睡眠周期
        expected_cycles = max(1, round(actual * 60 / 90))
        if cycles > 0:
            if cycles < expected_cycles - 1:
                sleep_advice.append(
                    "检测到 {} 个完整周期（Deep→REM），预期约 {} 个。"
                    "周期不完整意味着大脑的「内存整理」被中断，"
                    "影响学习记忆巩固和情绪调节。".format(cycles, expected_cycles)
                )
            else:
                sleep_advice.append(
                    "完成 {} 个完整睡眠周期，结构合理。".format(cycles)
                )

        # 深度 + REM
        if deep_pct < 10:
            sleep_advice.append(
                "深度睡眠仅 {:.1f}%（正常 15-25%）。这是身体修复的关键阶段。不足原因：\n"
                "  · 入睡过晚（错过生长激素分泌窗口）\n"
                "  · 睡前饮酒（酒精抑制深度睡眠）\n"
                "  · 年龄因素（30 岁后每 10 年下降约 2%）\n"
                "  · 缺乏白天运动（中等强度运动可增加当晚深度睡眠 25-30%）".format(deep_pct)
            )
        elif deep_pct < 15:
            sleep_advice.append(
                "深度睡眠 {:.1f}%，略低于理想范围（15-25%）。"
                "建议通过增加白天运动量和提前入睡时间来改善。".format(deep_pct)
            )
        elif deep_pct > 25:
            sleep_advice.append(
                "深度睡眠 {:.1f}%，非常优秀。身体物理恢复状态良好。".format(deep_pct)
            )

        if rem_pct < 15:
            sleep_advice.append(
                "REM {:.1f}%（正常 20-25%）。REM 是大脑「情绪排毒」的关键阶段。"
                "REM 不足与焦虑/抑郁风险升高相关。REM 集中在后半夜，"
                "起得太早会直接削减 REM。".format(rem_pct)
            )

        # 前后半夜
        first_half = sleep_analysis.get("first_half")
        second_half = sleep_analysis.get("second_half")
        if first_half and second_half:
            if first_half["deep_pct"] < 20 and type_minutes_total(sleep_analysis, "Deep") > 0:
                sleep_advice.append(
                    "前半夜深度仅 {:.1f}%，深度睡眠未集中在前半夜。"
                    "正常应在入睡后前 3-4 小时出现。"
                    "可能与入睡过晚、睡前兴奋状态有关。".format(first_half["deep_pct"])
                )
            if second_half["rem_pct"] < 20 and type_minutes_total(sleep_analysis, "REM") > 0:
                sleep_advice.append(
                    "后半夜 REM 偏少（{:.1f}%），可能因过早起床或后半夜频繁醒来。".format(
                        second_half["rem_pct"]
                    )
                )

        # 最长连续
        if max_cont < 60 and actual > 3:
            sleep_advice.append(
                "最长连续睡眠仅 {} 分钟，无法完成完整 90 分钟周期。"
                "这是睡眠质量差的强信号。".format(max_cont)
            )

    # 插入睡眠架构叙事
    arch_narrative = _build_sleep_architecture_narrative(sleep_analysis)
    combined_sleep = sleep_advice + arch_narrative

    if combined_sleep:
        sections.append(("😴 睡眠深度分析", combined_sleep))

    # ==================== 5. 交叉关联与风险信号 ====================
    cross = []

    if sleep_analysis and steps > 0:
        actual = sleep_analysis["actual_sleep_hours"]
        deep_pct = sleep_analysis["deep_pct"]
        if steps < 3000 and deep_pct < 15:
            cross.append(
                "低活动量（{} 步）+ 深度睡眠不足（{:.1f}%）形成恶性循环："
                "白天运动不够 → 夜间深度睡眠下降 → 第二天更疲惫不想动。"
                "打破循环的最佳入口：增加白天轻度运动（哪怕 30 分钟散步）。".format(
                    int(steps), deep_pct
                )
            )
        if steps > 10000 and actual < 6:
            cross.append(
                "高运动量（{} 步）但睡眠不足（{:.1f}h），身体处于"
                "「消耗大于恢复」状态。运动后若不给予充足睡眠，"
                "反而加速肌肉疲劳、免疫抑制。建议高运动日确保 ≥ 7.5h 睡眠。".format(
                    int(steps), actual
                )
            )

    if hr_analysis and sleep_analysis:
        resting = hr_analysis.get("night_resting") or hr_analysis["resting_est"]
        actual = sleep_analysis["actual_sleep_hours"]
        efficiency = sleep_analysis["sleep_efficiency"]

        if resting > 70 and efficiency < 85:
            cross.append(
                "夜间心率偏高（{:.0f} bpm）+ 睡眠效率低（{:.1f}%）= "
                "「身体疲惫但大脑无法放松」。可能处于过度疲劳或慢性压力状态。\n"
                "  · 睡前 1 小时放下电子设备\n"
                "  · 尝试渐进式肌肉放松法\n"
                "  · 持续一周以上考虑咨询医生".format(resting, efficiency)
            )

        if hr_analysis.get("rmssd_est") and hr_analysis["rmssd_est"] < 8 and actual < 6.5:
            cross.append(
                "HRV 低（{:.1f}）+ 睡眠不足（{:.1f}h）= 恢复能力严重受损。"
                "自主神经失衡状态，今天应避免高强度运动或重大决策，"
                "优先保证今晚睡眠。".format(hr_analysis["rmssd_est"], actual)
            )

    if sleep_analysis and sleep_analysis.get("bedtime_hour") is not None:
        bh = sleep_analysis["bedtime_hour"]
        if bh >= 2 and bh < 12 and energy < 200:
            cross.append(
                "凌晨 {} 入睡 + 低活动能量（{:.0f} kcal）= "
                "「白天久坐→晚上睡不着→恶性循环」。"
                "规律运动者入睡潜伏期平均缩短 55%。".format(
                    sleep_analysis["sleep_start"], energy
                )
            )

    # 心率 + 运动强度
    if hr_analysis and steps > 8000:
        max_hr = hr_analysis["max"]
        age_est_max = 190  # 假设年轻成人
        if max_hr > age_est_max * 0.85:
            cross.append(
                "今日最高心率 {:.0f} bpm 接近高强度阈值。如果不是有计划的"
                "间歇训练，建议控制运动强度在最大心率的 60-80% 区间。".format(max_hr)
            )

    if cross:
        sections.append(("🔗 交叉关联分析", cross))

    # ==================== 6. 综合评定 + 行动方案 ====================
    subscores, total, grade = _compute_subscores(data, hr_analysis, sleep_analysis)

    summary = []
    summary.append("健康评分: {}/100 — {}".format(total, grade))
    score_parts = []
    for name, (score, max_score) in subscores.items():
        bar_filled = int(score / max_score * 10)
        bar = "█" * bar_filled + "░" * (10 - bar_filled)
        score_parts.append("  {} {} {}/{}".format(name, bar, score, max_score))
    summary.append("\n".join(score_parts))

    sections.append(("📊 综合评定", summary))

    # 个性化行动方案
    action_plan = _generate_action_plan(data, hr_analysis, sleep_analysis)
    if action_plan:
        sections.append(("🎯 今日行动方案", action_plan))

    return sections


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def print_single_day_analysis(data):
    """打印单日完整分析。"""
    date = data.get("date", "未知日期")
    print(f"\n{'=' * 60}")
    print(f"  健康深度分析  {date}")
    print(f"{'=' * 60}")

    # 基础指标
    steps = data.get("steps", "N/A")
    energy = data.get("active_energy_kcal", "N/A")
    distance = data.get("distance_km", "N/A")
    print(f"\n📊 基础指标")
    print(f"   步数:     {steps}")
    if isinstance(energy, (int, float)):
        print(f"   活动能量:  {energy:.1f} kcal")
    if isinstance(distance, (int, float)):
        print(f"   步行距离:  {distance:.2f} km")
    if isinstance(steps, (int, float)) and isinstance(energy, (int, float)) and steps > 0:
        print(f"   每步能耗:  {energy / steps:.4f} kcal")
    if isinstance(steps, (int, float)) and isinstance(distance, (int, float)) and steps > 0:
        print(f"   平均步幅:  {distance * 1000 / steps:.2f} m")

    # 心率分析
    hr_analysis = analyze_heart_rate(data.get("heart_rate"))
    if hr_analysis:
        print(f"\n❤️ 心率详细（共 {hr_analysis['count']} 次测量）")
        print(f"   平均: {hr_analysis['avg']:.0f}  最高: {hr_analysis['max']:.0f}  最低: {hr_analysis['min']:.0f}  极差: {hr_analysis['range']:.0f}")
        print(f"   标准差: {hr_analysis['std_dev']:.1f} bpm")
        print(f"   静息心率(估): {hr_analysis['resting_est']:.0f} bpm")
        if hr_analysis.get("night_resting"):
            print(f"   夜间静息(精): {hr_analysis['night_resting']:.0f} bpm")
        if hr_analysis.get("rmssd_est"):
            print(f"   HRV (RMSSD≈): {hr_analysis['rmssd_est']:.1f}")
        if hr_analysis.get("ans_state"):
            print(f"   自主神经状态: {hr_analysis['ans_state']}")
        if hr_analysis.get("recovery_1min"):
            print(f"   运动后恢复:   峰值后 Δ{hr_analysis['recovery_1min']} bpm")
        print(f"   时段分布:")
        for period, pdata in hr_analysis["periods"].items():
            if pdata:
                print(f"     {period}: 平均 {pdata['avg']:.0f}  范围 {pdata['min']:.0f}-{pdata['max']:.0f}  ({pdata['count']}次)")
        spikes = hr_analysis.get("spike_events", [])
        if spikes:
            print(f"   心率突变事件: {len(spikes)} 次")

    # 睡眠分析
    sleep_analysis = analyze_sleep(data.get("sleep"))
    if sleep_analysis:
        print(f"\n😴 睡眠详细")
        print(f"   入睡: {sleep_analysis['sleep_start']}  醒来: {sleep_analysis['sleep_end']}")
        print(f"   总时长: {sleep_analysis['total_hours']:.1f}h  实际睡眠: {sleep_analysis['actual_sleep_hours']:.1f}h")
        print(f"   睡眠效率: {sleep_analysis['sleep_efficiency']:.1f}%")
        print(f"   睡眠周期: {sleep_analysis['cycle_count']} 个完整周期")
        print(f"   碎片化指数: {sleep_analysis['fragmentation_idx']:.1f} (切换/h)")
        print(f"   最长连续: {sleep_analysis['max_continuous_min']} 分钟")
        if sleep_analysis["awake_episodes"] > 0:
            print(f"   夜间醒来: {sleep_analysis['awake_episodes']} 次")
        print(f"   睡眠阶段:")
        for stage, hours in sleep_analysis["stages"].items():
            pct_key = f"{stage.lower()}_pct"
            pct = sleep_analysis.get(pct_key, "")
            pct_str = f" ({pct:.1f}%)" if isinstance(pct, float) else ""
            print(f"     {stage}: {hours:.1f}h{pct_str}")
        first_h = sleep_analysis.get("first_half")
        second_h = sleep_analysis.get("second_half")
        if first_h and second_h:
            print(f"   前半夜: Deep {first_h['deep_pct']:.1f}%  REM {first_h['rem_pct']:.1f}%")
            print(f"   后半夜: Deep {second_h['deep_pct']:.1f}%  REM {second_h['rem_pct']:.1f}%")

    # 深度健康分析与建议
    advice_sections = generate_health_advice(data, hr_analysis, sleep_analysis)
    if advice_sections:
        print(f"\n{'─' * 60}")
        print(f"  💡 深度分析与个性化建议")
        print(f"{'─' * 60}")
        for title, items in advice_sections:
            print(f"\n  {title}")
            for item in items:
                lines = item.split("\n")
                print(f"    · {lines[0]}")
                for line in lines[1:]:
                    print(f"      {line}")

    print()


def print_multi_day_report(entries):
    """打印多日趋势报告（含趋势预警）。"""
    if not entries:
        print("没有找到健康数据文件")
        return

    print(f"\n{'=' * 60}")
    print(f"  健康趋势报告（{len(entries)} 天）")
    print(f"  {entries[0].get('date', '?')} ~ {entries[-1].get('date', '?')}")
    print(f"{'=' * 60}")

    # 收集每日指标用于趋势分析
    daily_metrics = []

    # 步数趋势
    print(f"\n📊 步数趋势")
    print(f"  {'日期':<14}{'步数':>8}  {'图表'}")
    print(f"  {'-' * 40}")
    step_values = []
    for e in entries:
        s = e.get("steps", 0)
        if isinstance(s, (int, float)):
            step_values.append(s)
    max_steps = max(step_values) if step_values else 1

    for e in entries:
        d = e.get("date", "?")
        s = e.get("steps", 0)
        if isinstance(s, (int, float)):
            bar = "█" * min(int(s / max_steps * 20), 20) if max_steps > 0 else ""
            print(f"  {d}  {s:>8.0f}  {bar}")

    if step_values:
        print(f"  {'-' * 40}")
        avg_steps = sum(step_values) / len(step_values)
        print(f"  {'平均':<12}  {avg_steps:>8.0f}")

    # 每日心率范围
    print(f"\n❤️ 心率范围")
    print(f"  {'日期':<14}{'最低':>6}{'平均':>6}{'最高':>6}{'静息':>6}{'HRV':>6}")
    print(f"  {'-' * 48}")
    resting_values = []
    hrv_values = []
    for e in entries:
        hr = analyze_heart_rate(e.get("heart_rate"))
        if hr:
            resting = hr.get("night_resting") or hr["resting_est"]
            resting_values.append(resting)
            rmssd_str = f"{hr['rmssd_est']:>5.1f}" if hr.get("rmssd_est") else "    -"
            if hr.get("rmssd_est"):
                hrv_values.append(hr["rmssd_est"])
            print(f"  {e.get('date', '?')}  {hr['min']:>5.0f} {hr['avg']:>5.0f} {hr['max']:>5.0f} {resting:>5.0f} {rmssd_str}")

    # 每日睡眠
    print(f"\n😴 睡眠时长")
    print(f"  {'日期':<14}{'实际':>6}{'效率%':>6}{'深度%':>6}{'REM%':>6}  {'图表'}")
    print(f"  {'-' * 55}")
    sleep_hours_list = []
    deep_pct_list = []
    efficiency_list = []
    for e in entries:
        sl = analyze_sleep(e.get("sleep"))
        if sl:
            sleep_hours_list.append(sl["actual_sleep_hours"])
            deep_pct_list.append(sl["deep_pct"])
            efficiency_list.append(sl["sleep_efficiency"])
            bar = "█" * min(int(sl["actual_sleep_hours"] / 10 * 20), 20)
            print(f"  {e.get('date', '?')}  {sl['actual_sleep_hours']:>5.1f}h {sl['sleep_efficiency']:>5.1f} {sl['deep_pct']:>5.1f} {sl['rem_pct']:>5.1f}  {bar}")

    # ==================== 趋势预警 ====================
    trend_alerts = []

    # 步数连续下降
    if len(step_values) >= 3:
        last3 = step_values[-3:]
        if last3[0] > last3[1] > last3[2]:
            trend_alerts.append(
                "⚠️ 步数连续 3 天下降（{}→{}→{}），活动量呈下滑趋势。"
                "注意是否进入久坐-疲劳的恶性循环。".format(
                    int(last3[0]), int(last3[1]), int(last3[2])
                )
            )
        avg_steps = sum(step_values) / len(step_values)
        if avg_steps < 5000:
            trend_alerts.append(
                "⚠️ 近 {} 天平均步数仅 {:.0f}，长期低于 5000 步/天会显著增加代谢综合征风险。".format(
                    len(step_values), avg_steps
                )
            )

    # 静息心率趋势
    if len(resting_values) >= 3:
        last3r = resting_values[-3:]
        if all(r > 70 for r in last3r):
            trend_alerts.append(
                "⚠️ 连续 3 天夜间静息心率 > 70 bpm（{}），"
                "可能提示慢性压力积累或身体恢复不足。建议排查压力源。".format(
                    ", ".join(f"{r:.0f}" for r in last3r)
                )
            )
        if last3r[0] < last3r[1] < last3r[2] and last3r[2] - last3r[0] > 5:
            trend_alerts.append(
                "⚠️ 静息心率连续上升（{:.0f}→{:.0f}→{:.0f} bpm），"
                "可能是过度疲劳、感染前期或压力累积的信号。".format(*last3r)
            )

    # HRV 趋势
    if len(hrv_values) >= 3:
        last3h = hrv_values[-3:]
        if last3h[0] > last3h[1] > last3h[2]:
            trend_alerts.append(
                "⚠️ HRV 连续下降（{:.1f}→{:.1f}→{:.1f}），"
                "自主神经调节能力在持续退化。建议增加恢复性活动（散步、冥想、充足睡眠）。".format(
                    *last3h
                )
            )

    # 睡眠连续不足
    if len(sleep_hours_list) >= 3:
        last3s = sleep_hours_list[-3:]
        if all(s < 6.5 for s in last3s):
            total_deficit = sum(7 - s for s in last3s)
            trend_alerts.append(
                "🚨 连续 3 天睡眠不足 6.5h，累积睡眠债约 {:.1f} 小时。"
                "研究显示连续 3 天不足 6 小时后，认知表现等同于一晚完全没睡。"
                "请务必优先保证今晚睡眠。".format(total_deficit)
            )

    # 深度睡眠持续偏低
    if len(deep_pct_list) >= 3:
        if all(d < 13 for d in deep_pct_list[-3:]):
            trend_alerts.append(
                "⚠️ 连续 3 天深度睡眠占比 < 13%，身体修复长期不足。"
                "建议：增加白天运动量、提前入睡时间、减少睡前酒精摄入。"
            )

    if trend_alerts:
        print(f"\n{'─' * 60}")
        print(f"  🔔 趋势预警")
        print(f"{'─' * 60}")
        for alert in trend_alerts:
            print(f"  {alert}")

    # 综合建议（基于最新一天）
    latest = entries[-1]
    hr_a = analyze_heart_rate(latest.get("heart_rate"))
    sl_a = analyze_sleep(latest.get("sleep"))
    advice_sections = generate_health_advice(latest, hr_a, sl_a)
    if advice_sections:
        print(f"\n{'─' * 60}")
        print(f"  💡 最新一日深度分析（{latest.get('date', '?')}）")
        print(f"{'─' * 60}")
        for title, items in advice_sections:
            print(f"\n  {title}")
            for item in items:
                lines = item.split("\n")
                print(f"    · {lines[0]}")
                for line in lines[1:]:
                    print(f"      {line}")

    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def print_usage():
    print("""Apple Health 数据分析工具

用法:
  python health_tool.py analyze  <file>                   分析单日数据
  python health_tool.py analyze  <dir>  [--days 7]        分析目录中所有数据
  python health_tool.py report   <dir>  [--days 7]        多日趋势报告
  python health_tool.py today    [dir]                    分析今日数据

数据来源:
  iOS 快捷指令每日自动导出到 iCloud Drive 的文件
  默认目录: ~/Library/Mobile Documents/com~apple~CloudDocs/Shortcuts/Health/

示例:
  python health_tool.py today
  python health_tool.py analyze health_2026-03-10.txt
  python health_tool.py report ~/Library/Mobile\\ Documents/com~apple~CloudDocs/Shortcuts/Health/ --days 14""")


def parse_args(args):
    """解析 --days N 参数。"""
    days = None
    remaining = []
    i = 0
    while i < len(args):
        if args[i] == "--days" and i + 1 < len(args):
            try:
                days = int(args[i + 1])
            except ValueError:
                print(f"无效的天数: {args[i + 1]}", file=sys.stderr)
                sys.exit(1)
            i += 2
        else:
            remaining.append(args[i])
            i += 1
    return remaining, days


def _cleanup_old_health_files(dirpath, keep_date_str):
    """清理旧的健康数据文件，只保留指定日期的文件。"""
    dirpath = Path(dirpath)
    removed = 0
    for f in dirpath.glob("health_*"):
        if f.is_file() and keep_date_str not in f.name:
            f.unlink()
            removed += 1
    if removed:
        print(f"\n🗑️ 已清理 {removed} 个旧文件，仅保留 {keep_date_str} 的数据")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    command = sys.argv[1]
    rest, days = parse_args(sys.argv[2:])

    if command == "analyze":
        if not rest:
            print("需要文件或目录路径", file=sys.stderr)
            sys.exit(1)
        target = Path(rest[0])
        if target.is_file():
            data = load_health_file(target)
            if data:
                print_single_day_analysis(data)
        elif target.is_dir():
            entries = load_health_dir(target, days)
            for e in entries:
                print_single_day_analysis(e)
        else:
            print(f"路径不存在: {target}", file=sys.stderr)
            sys.exit(1)

    elif command == "report":
        dirpath = rest[0] if rest else DEFAULT_HEALTH_DIR
        entries = load_health_dir(dirpath, days or 7)
        print_multi_day_report(entries)

    elif command == "today":
        dirpath = rest[0] if rest else DEFAULT_HEALTH_DIR
        today_str = datetime.now().strftime("%Y-%m-%d")
        dirpath = Path(dirpath)

        found = None
        for suffix in (".json", ".txt"):
            candidate = dirpath / f"health_{today_str}{suffix}"
            if candidate.exists():
                found = candidate
                break

        if found:
            data = load_health_file(found)
            if data:
                print_single_day_analysis(data)
                # 清理旧文件：只保留今天的，删除其他 health_*.json/txt
                _cleanup_old_health_files(dirpath, today_str)
        else:
            print(f"未找到今日数据文件: health_{today_str}.json/txt")
            print(f"目录: {dirpath}")
            sys.exit(1)

    else:
        print(f"未知命令: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
