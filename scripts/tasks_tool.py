#!/usr/bin/env python3
"""待办事项管理工具 — OpenClaw ↔ iCloud ↔ iPhone 快捷指令。

数据流:
  1. AI 对话中用户提到待办 → AI 调用本工具写入本地 JSON
  2. 每晚 22:00 (或手动) 同步到 iCloud Drive
  3. iPhone 快捷指令读取 JSON → 写入备忘录/提醒事项

本地文件: ~/.openclaw/tasks.json
iCloud 路径: iCloud Drive/Shortcuts/Tasks/tasks.json

用法:
  python tasks_tool.py add "给客户发方案" --date 2026-03-12 --time 14:00 --priority high --notes "附上报价单" --target reminder
  python tasks_tool.py add "学习笔记整理" --target note --notes "React Server Components要点"
  python tasks_tool.py list                          # 列出所有待办
  python tasks_tool.py list --date 2026-03-12        # 列出指定日期
  python tasks_tool.py list --date tomorrow          # 列出明天
  python tasks_tool.py done <id>                     # 标记完成
  python tasks_tool.py remove <id>                   # 删除
  python tasks_tool.py edit <id> --title "新标题" --date 2026-03-13 --time 10:00
  python tasks_tool.py clear --before 2026-03-10     # 清理旧任务
  python tasks_tool.py show                          # 显示完整 JSON 内容
  python tasks_tool.py sync                          # 上传到 iCloud Drive
  python tasks_tool.py sync --download               # 从 iCloud 下载（覆盖本地）
"""

import json
import os
import sys
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

TASKS_DIR = os.path.expanduser("~/.openclaw")
TASKS_FILE = os.path.join(TASKS_DIR, "tasks.json")
ICLOUD_TASKS_PATH = "Shortcuts/Tasks"
ICLOUD_TASKS_FILENAME = "tasks.json"

# ---------------------------------------------------------------------------
# 数据存储
# ---------------------------------------------------------------------------

def _ensure_dir():
    os.makedirs(TASKS_DIR, exist_ok=True)


def _load_tasks():
    """加载本地 tasks.json。"""
    _ensure_dir()
    if not os.path.exists(TASKS_FILE):
        return {"updated_at": None, "tasks": []}
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "tasks" not in data:
            data["tasks"] = []
        return data
    except (json.JSONDecodeError, IOError):
        return {"updated_at": None, "tasks": []}


def _save_tasks(data):
    """保存到本地 tasks.json。"""
    _ensure_dir()
    data["updated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _gen_id():
    """生成短 ID。"""
    return uuid.uuid4().hex[:8]


def _resolve_date(date_str):
    """解析日期字符串，支持 today/tomorrow/后天 等。"""
    if not date_str:
        return None
    lower = date_str.strip().lower()
    today = datetime.now().date()
    mapping = {
        "today": today,
        "今天": today,
        "tomorrow": today + timedelta(days=1),
        "明天": today + timedelta(days=1),
        "后天": today + timedelta(days=2),
        "大后天": today + timedelta(days=3),
    }
    if lower in mapping:
        return mapping[lower].strftime("%Y-%m-%d")
    # 尝试解析标准格式
    for fmt in ("%Y-%m-%d", "%m-%d", "%m/%d"):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if fmt in ("%m-%d", "%m/%d"):
                dt = dt.replace(year=today.year)
                if dt.date() < today:
                    dt = dt.replace(year=today.year + 1)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str.strip()


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------

def cmd_add(args):
    """添加待办。"""
    if not args:
        print("用法: tasks_tool.py add <标题> [选项]")
        print("  --date <日期>      截止日期 (YYYY-MM-DD/tomorrow/明天/后天)")
        print("  --time <时间>      提醒时间 (HH:MM)")
        print("  --priority <级别>  优先级 (high/medium/low)")
        print("  --notes <备注>     详细备注")
        print("  --target <目标>    reminder(提醒事项) 或 note(备忘录), 默认 reminder")
        print("  --list <列表名>    提醒事项列表名/备忘录文件夹名")
        return

    title = args[0]
    opts = _parse_opts(args[1:])

    task = {
        "id": _gen_id(),
        "title": title,
        "date": _resolve_date(opts.get("date")),
        "time": opts.get("time"),
        "priority": opts.get("priority", "medium"),
        "notes": opts.get("notes", ""),
        "target": opts.get("target", "reminder"),
        "list": opts.get("list", ""),
        "status": "pending",
        "created_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    data = _load_tasks()
    data["tasks"].append(task)
    _save_tasks(data)

    target_label = "提醒事项" if task["target"] == "reminder" else "备忘录"
    date_str = task["date"] or "无日期"
    time_str = task["time"] or ""
    print(f"✅ 已添加 [{task['id']}] {title}")
    print(f"   日期: {date_str} {time_str}  优先级: {task['priority']}  目标: {target_label}")


def cmd_list(args):
    """列出待办。"""
    opts = _parse_opts(args)
    filter_date = _resolve_date(opts.get("date"))
    filter_status = opts.get("status")
    filter_target = opts.get("target")

    data = _load_tasks()
    tasks = data["tasks"]

    if filter_date:
        tasks = [t for t in tasks if t.get("date") == filter_date]
    if filter_status:
        tasks = [t for t in tasks if t.get("status") == filter_status]
    if filter_target:
        tasks = [t for t in tasks if t.get("target") == filter_target]

    if not tasks:
        print("📋 没有匹配的待办事项")
        return

    # 按日期分组
    by_date = {}
    no_date = []
    for t in tasks:
        d = t.get("date")
        if d:
            by_date.setdefault(d, []).append(t)
        else:
            no_date.append(t)

    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"\n📋 待办事项（共 {len(tasks)} 项）")
    print(f"{'─' * 50}")

    for date_key in sorted(by_date.keys()):
        if date_key == today:
            label = f"📅 {date_key}（今天）"
        elif date_key == tomorrow:
            label = f"📅 {date_key}（明天）"
        else:
            label = f"📅 {date_key}"
        print(f"\n  {label}")
        for t in by_date[date_key]:
            _print_task(t)

    if no_date:
        print(f"\n  📅 无日期")
        for t in no_date:
            _print_task(t)

    print()


def _print_task(t):
    """打印单个待办。"""
    status_icon = "✅" if t.get("status") == "done" else "⬜"
    priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(t.get("priority", "medium"), "⚪")
    target_icon = "📝" if t.get("target") == "note" else "⏰"
    time_str = f" {t['time']}" if t.get("time") else ""

    line = f"    {status_icon} [{t['id']}] {priority_icon} {t['title']}{time_str} {target_icon}"
    if t.get("list"):
        line += f" 📂{t['list']}"
    print(line)
    if t.get("notes"):
        for note_line in t["notes"].split("\n"):
            print(f"       {note_line}")


def cmd_done(args):
    """标记待办完成。"""
    if not args:
        print("用法: tasks_tool.py done <id>")
        return

    task_id = args[0]
    data = _load_tasks()
    for t in data["tasks"]:
        if t["id"] == task_id:
            t["status"] = "done"
            _save_tasks(data)
            print(f"✅ 已完成: {t['title']}")
            return

    print(f"❌ 未找到 ID: {task_id}")


def cmd_remove(args):
    """删除待办。"""
    if not args:
        print("用法: tasks_tool.py remove <id>")
        return

    task_id = args[0]
    data = _load_tasks()
    original_len = len(data["tasks"])
    data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]

    if len(data["tasks"]) < original_len:
        _save_tasks(data)
        print(f"🗑️  已删除 ID: {task_id}")
    else:
        print(f"❌ 未找到 ID: {task_id}")


def cmd_edit(args):
    """编辑待办。"""
    if not args:
        print("用法: tasks_tool.py edit <id> --title <新标题> --date <日期> --time <时间> ...")
        return

    task_id = args[0]
    opts = _parse_opts(args[1:])

    data = _load_tasks()
    for t in data["tasks"]:
        if t["id"] == task_id:
            if "title" in opts:
                t["title"] = opts["title"]
            if "date" in opts:
                t["date"] = _resolve_date(opts["date"])
            if "time" in opts:
                t["time"] = opts["time"]
            if "priority" in opts:
                t["priority"] = opts["priority"]
            if "notes" in opts:
                t["notes"] = opts["notes"]
            if "target" in opts:
                t["target"] = opts["target"]
            if "list" in opts:
                t["list"] = opts["list"]

            _save_tasks(data)
            print(f"✏️  已更新 [{task_id}] {t['title']}")
            _print_task(t)
            return

    print(f"❌ 未找到 ID: {task_id}")


def cmd_clear(args):
    """清理已完成或旧任务。"""
    opts = _parse_opts(args)
    before_date = opts.get("before")
    clear_done = "--done" in args

    data = _load_tasks()
    original_len = len(data["tasks"])

    if clear_done:
        data["tasks"] = [t for t in data["tasks"] if t.get("status") != "done"]
    elif before_date:
        before = _resolve_date(before_date)
        data["tasks"] = [
            t for t in data["tasks"]
            if not t.get("date") or t["date"] >= before
        ]
    else:
        # 默认清理已完成的
        data["tasks"] = [t for t in data["tasks"] if t.get("status") != "done"]

    removed = original_len - len(data["tasks"])
    _save_tasks(data)
    print(f"🧹 已清理 {removed} 项，剩余 {len(data['tasks'])} 项")


def cmd_show(args):
    """显示完整 JSON。"""
    data = _load_tasks()
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_sync(args):
    """同步到/从 iCloud Drive。

    默认上传本地 → iCloud。加 --download 从 iCloud 覆盖本地。
    """
    download_mode = "--download" in args

    # 延迟导入 iCloud 工具
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, scripts_dir)

    try:
        # 复用 icloud_tool 的认证逻辑
        os.environ.setdefault('ICLOUD_CHINA', '1')
        if os.environ.get('ICLOUD_CHINA', '1') == '1':
            os.environ['icloud_china'] = '1'

        from pyicloud import PyiCloudService

        # 尝试 session 恢复
        try:
            from icloud_auth import get_api_with_session
            api = get_api_with_session()
        except Exception:
            username = os.environ.get("ICLOUD_USERNAME")
            password = os.environ.get("ICLOUD_PASSWORD")
            if not username or not password:
                print("❌ 需要 iCloud 凭证。设置 ICLOUD_USERNAME 和 ICLOUD_PASSWORD 环境变量")
                sys.exit(1)
            api = PyiCloudService(username, password, china_mainland=True)

        drive = api.drive

        # 确保目标目录存在
        _ensure_icloud_dir(drive)

        if download_mode:
            _sync_download(drive)
        else:
            _sync_upload(drive)

    except ImportError:
        print("❌ 请先安装 pyicloud: pip install pyicloud")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 同步失败: {e}")
        sys.exit(1)


def _ensure_icloud_dir(drive):
    """确保 iCloud Drive/Shortcuts/Tasks/ 和 Shortcuts/Notes/ 目录存在。"""
    # 检查 Shortcuts 目录
    try:
        shortcuts = drive["Shortcuts"]
    except (KeyError, IndexError):
        print("📁 创建 Shortcuts 目录...")
        drive.mkdir("Shortcuts")
        shortcuts = drive["Shortcuts"]

    # 检查 Tasks 子目录
    try:
        _ = shortcuts["Tasks"]
    except (KeyError, IndexError):
        print("📁 创建 Tasks 目录...")
        shortcuts.mkdir("Tasks")

    # 检查 Notes 子目录
    try:
        _ = shortcuts["Notes"]
    except (KeyError, IndexError):
        print("📁 创建 Notes 目录...")
        shortcuts.mkdir("Notes")


def _sync_upload(drive):
    """上传本地 tasks.json 到 iCloud Drive（覆盖模式，按类型分文件夹）。

    根据 target 字段分到两个独立文件夹：
    - Shortcuts/Tasks/tasks_latest.json  — 提醒事项 (target=reminder)
    - Shortcuts/Notes/notes_latest.json  — 备忘录 (target=note)

    每个文件夹只有一个文件，快捷指令直接读取，无需筛选。
    """
    data = _load_tasks()
    pending = [t for t in data["tasks"] if t.get("status") != "done"]

    if not pending:
        print("📋 没有待处理的待办，跳过同步")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # 按 target 分类（默认归入 reminder）
    reminders = [t for t in pending if t.get("target", "reminder") != "note"]
    notes = [t for t in pending if t.get("target") == "note"]

    tasks_folder = drive["Shortcuts"]["Tasks"]
    notes_folder = drive["Shortcuts"]["Notes"]

    # 上传提醒事项
    if reminders:
        _upload_file(tasks_folder, "tasks_latest.json", {
            "updated_at": now_str,
            "date": today_str,
            "synced_from": "openclaw",
            "type": "reminder",
            "tasks": reminders,
        })
        print(f"⏰ 已同步 {len(reminders)} 项提醒事项 → Shortcuts/Tasks/tasks_latest.json")
    else:
        _delete_old_file(tasks_folder, "tasks_latest.json")
        print("⏰ 无提醒事项，已清理旧文件")

    # 上传备忘录
    if notes:
        _upload_file(notes_folder, "notes_latest.json", {
            "updated_at": now_str,
            "date": today_str,
            "synced_from": "openclaw",
            "type": "note",
            "tasks": notes,
        })
        print(f"📝 已同步 {len(notes)} 条备忘录 → Shortcuts/Notes/notes_latest.json")
    else:
        _delete_old_file(notes_folder, "notes_latest.json")
        print("📝 无备忘录，已清理旧文件")


def _delete_old_file(folder, filename):
    """删除 iCloud Drive 中的旧文件（如果存在）。"""
    try:
        old_file = folder[filename]
        old_file.delete()
    except (KeyError, IndexError):
        pass


def _upload_file(folder, filename, data_dict):
    """先删旧文件，再上传新文件到 iCloud Drive。"""
    _delete_old_file(folder, filename)

    tmp_path = os.path.join(TASKS_DIR, filename)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=2)
    try:
        with open(tmp_path, "rb") as f:
            folder.upload(f)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _sync_download(drive):
    """从 iCloud Drive 下载最新的待办文件合并到本地。"""
    try:
        target_folder = drive["Shortcuts"]["Tasks"]
        # 优先读 tasks_latest.json，其次按日期文件名
        today_str = datetime.now().strftime("%Y-%m-%d")
        candidates = [
            "tasks_latest.json",
            f"tasks_{today_str}.json",
            "tasks_sync.json",  # 兼容旧格式
        ]
        for name in candidates:
            try:
                node = target_folder[name]
                response = node.open(stream=True)
                content = response.raw.read()
                icloud_data = json.loads(content.decode("utf-8"))

                # 合并：iCloud 的任务覆盖本地同 ID 的
                local_data = _load_tasks()
                local_ids = {t["id"] for t in local_data["tasks"]}
                icloud_ids = {t["id"] for t in icloud_data.get("tasks", [])}

                # 保留本地独有的 + iCloud 的全部
                merged = [t for t in local_data["tasks"] if t["id"] not in icloud_ids]
                merged.extend(icloud_data.get("tasks", []))

                local_data["tasks"] = merged
                _save_tasks(local_data)
                print(f"⬇️  已从 iCloud 下载并合并 {len(icloud_data.get('tasks', []))} 项待办")
                return
            except (KeyError, IndexError):
                continue

        print("❌ iCloud Drive 中未找到待办文件")
    except Exception as e:
        print(f"❌ 下载失败: {e}")


# ---------------------------------------------------------------------------
# 参数解析
# ---------------------------------------------------------------------------

def _parse_opts(args):
    """解析 --key value 形式的参数。"""
    opts = {}
    i = 0
    while i < len(args):
        if args[i].startswith("--") and i + 1 < len(args) and not args[i + 1].startswith("--"):
            key = args[i][2:]
            opts[key] = args[i + 1]
            i += 2
        else:
            i += 1
    return opts


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def print_usage():
    print("""待办事项管理工具 (OpenClaw ↔ iCloud ↔ iPhone)

用法:
  python tasks_tool.py add <标题> [选项]     添加待办
  python tasks_tool.py list [选项]           列出待办
  python tasks_tool.py done <id>             标记完成
  python tasks_tool.py remove <id>           删除
  python tasks_tool.py edit <id> [选项]      编辑
  python tasks_tool.py clear [--done|--before DATE]  清理
  python tasks_tool.py show                  显示 JSON
  python tasks_tool.py sync                  上传到 iCloud
  python tasks_tool.py sync --download       从 iCloud 下载

选项:
  --date <日期>      YYYY-MM-DD / tomorrow / 明天 / 后天
  --time <时间>      HH:MM
  --priority <级别>  high / medium / low
  --notes <备注>     详细说明
  --target <目标>    reminder(提醒事项) / note(备忘录)
  --list <列表名>    提醒事项列表名 / 备忘录文件夹名

示例:
  python tasks_tool.py add "开会" --date tomorrow --time 14:00 --priority high
  python tasks_tool.py add "读书笔记" --target note --notes "第三章要点整理"
  python tasks_tool.py list --date tomorrow
  python tasks_tool.py sync""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    command = sys.argv[1]
    rest = sys.argv[2:]

    commands = {
        "add": cmd_add,
        "list": cmd_list,
        "done": cmd_done,
        "remove": cmd_remove,
        "edit": cmd_edit,
        "clear": cmd_clear,
        "show": cmd_show,
        "sync": cmd_sync,
    }

    if command in commands:
        commands[command](rest)
    else:
        print(f"未知命令: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
