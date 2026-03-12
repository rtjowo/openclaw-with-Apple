#!/usr/bin/env python3
"""配置 macOS launchd 定时任务 — 每晚 22:00 自动同步待办到 iCloud。

用法:
  python setup_tasks_cron.py install    # 安装定时任务
  python setup_tasks_cron.py uninstall  # 卸载定时任务
  python setup_tasks_cron.py status     # 查看状态

原理:
  在 ~/Library/LaunchAgents/ 创建 plist 文件,
  macOS 的 launchd 系统在每天 22:00 自动执行:
    python3 /path/to/scripts/tasks_tool.py sync
"""

import os
import subprocess
import sys
from pathlib import Path

LABEL = "com.openclaw.tasks-sync"
PLIST_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST_PATH = os.path.join(PLIST_DIR, f"{LABEL}.plist")

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_TOOL = os.path.join(SCRIPTS_DIR, "tasks_tool.py")
LOG_DIR = os.path.expanduser("~/.openclaw/logs")


def _find_python():
    """找到 python3 的绝对路径。"""
    for p in ["/usr/bin/python3", "/usr/local/bin/python3", "/opt/homebrew/bin/python3"]:
        if os.path.exists(p):
            return p
    result = subprocess.run(["which", "python3"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout.strip()
    return "python3"


def _generate_plist(python_path):
    """生成 launchd plist XML。"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{TASKS_TOOL}</string>
        <string>sync</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>22</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{LOG_DIR}/tasks-sync.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/tasks-sync-error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
        <key>ICLOUD_CHINA</key>
        <string>1</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install():
    """安装 launchd 定时任务。"""
    python_path = _find_python()
    print(f"🐍 Python: {python_path}")
    print(f"📄 脚本: {TASKS_TOOL}")

    if not os.path.exists(TASKS_TOOL):
        print(f"❌ tasks_tool.py 不存在: {TASKS_TOOL}")
        sys.exit(1)

    os.makedirs(PLIST_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    plist_content = _generate_plist(python_path)

    # 如果已存在，先卸载
    if os.path.exists(PLIST_PATH):
        print("⚠️  已有旧配置，先卸载...")
        subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True)

    with open(PLIST_PATH, "w") as f:
        f.write(plist_content)

    result = subprocess.run(["launchctl", "load", PLIST_PATH], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"✅ 定时任务已安装")
        print(f"   每天 22:00 自动同步待办到 iCloud Drive")
        print(f"   日志: {LOG_DIR}/tasks-sync.log")
        print(f"   配置: {PLIST_PATH}")
        print(f"\n💡 注意: 需要确保 ICLOUD_USERNAME 和 ICLOUD_PASSWORD 环境变量已设置")
        print(f"   或者 iCloud session 缓存有效 (~/.pyicloud/)")
    else:
        print(f"❌ 安装失败: {result.stderr}")
        sys.exit(1)


def uninstall():
    """卸载定时任务。"""
    if not os.path.exists(PLIST_PATH):
        print("ℹ️  未安装定时任务")
        return

    result = subprocess.run(["launchctl", "unload", PLIST_PATH], capture_output=True, text=True)
    os.remove(PLIST_PATH)
    print(f"✅ 定时任务已卸载")


def status():
    """查看定时任务状态。"""
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    lines = [l for l in result.stdout.split("\n") if LABEL in l]
    if lines:
        print(f"✅ 定时任务运行中:")
        for l in lines:
            print(f"   {l}")
    else:
        print(f"❌ 定时任务未运行")

    if os.path.exists(PLIST_PATH):
        print(f"📄 配置文件存在: {PLIST_PATH}")
    else:
        print(f"📄 配置文件不存在")

    log_file = os.path.join(LOG_DIR, "tasks-sync.log")
    if os.path.exists(log_file):
        print(f"\n📋 最近日志:")
        with open(log_file) as f:
            lines = f.readlines()
            for l in lines[-5:]:
                print(f"   {l.rstrip()}")


def main():
    if len(sys.argv) < 2:
        print("用法: python setup_tasks_cron.py [install|uninstall|status]")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    elif cmd == "status":
        status()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
