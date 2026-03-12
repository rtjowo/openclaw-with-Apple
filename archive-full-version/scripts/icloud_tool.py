#!/usr/bin/env python3
"""
Apple iCloud 命令行工具（非交互式，适配 AI 环境）

认证优先级：
  1. 优先尝试 session 缓存（免密，由之前登录生成）
  2. session 不可用时，使用环境变量 ICLOUD_USERNAME + ICLOUD_PASSWORD 登录
  3. 如需 2FA，打印提示并退出（退出码 2），等用户提供验证码后用 verify 命令完成

用法:
  python icloud_tool.py login                # 登录（如需2FA会提示并退出）
  python icloud_tool.py verify <6位验证码>    # 输入2FA验证码完成登录
  python icloud_tool.py [photos|drive|devices|find] [子命令]

环境变量:
  ICLOUD_USERNAME  - Apple ID
  ICLOUD_PASSWORD  - 主密码 (非应用专用密码)
  ICLOUD_CHINA     - 设为 1 表示中国大陆用户（默认 1）
"""

import sys
import os
import json
from datetime import datetime

# 中国大陆用户设置
if os.environ.get('ICLOUD_CHINA', '1') == '1':
    os.environ['icloud_china'] = '1'

try:
    from pyicloud import PyiCloudService
except ImportError:
    print("请先安装 pyicloud: pip install pyicloud")
    sys.exit(1)

# 导入认证模块（可选）
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

try:
    from icloud_auth import get_api_with_session, try_restore_session
    HAS_AUTH_MODULE = True
except ImportError:
    HAS_AUTH_MODULE = False


# ─── 认证 ─────────────────────────────────────────────

def get_api(require_password=False):
    """连接 iCloud — 优先 session，fallback 到密码。全程非交互式。"""
    china = os.environ.get('icloud_china') == '1'
    username = os.environ.get('ICLOUD_USERNAME')
    password = os.environ.get('ICLOUD_PASSWORD')

    if not require_password and HAS_AUTH_MODULE:
        if username:
            api, error = try_restore_session(username, china_mainland=china)
        else:
            try:
                api = get_api_with_session(china_mainland=china)
                return api
            except SystemExit:
                api, error = None, "session 不可用"
        if api:
            print("✅ 通过缓存 session 连接成功\n")
            return api
        # session 不可用：如果有密码就静默 fallback，没密码才报错
        if not username or not password:
            print(f"❌ iCloud session 已过期或不可用（{error}）")
            if not username:
                print("   请设置环境变量：")
                print("     export ICLOUD_USERNAME=\"你的Apple ID邮箱\"")
                print("     export ICLOUD_PASSWORD=\"你的密码\"")
                print("     python scripts/icloud_tool.py login")
            else:
                print("   请设置密码环境变量：")
                print("     export ICLOUD_PASSWORD=\"你的密码\"")
                print("     python scripts/icloud_tool.py login")
            sys.exit(1)

    print(f'🍎 正在连接 iCloud{"(中国大陆)" if china else ""}...')
    api = PyiCloudService(username, password, china_mainland=china)

    if api.requires_2fa:
        print("\n🔐 需要双重认证！")
        print("请查看 iPhone/iPad/Mac 上的 6 位验证码弹窗，然后运行：")
        print(f"  python icloud_tool.py verify <6位验证码>")
        sys.exit(2)

    print("✅ 已连接!\n")
    return api


def cmd_login():
    """登录命令"""
    api = get_api(require_password=True)
    _verify_all_services(api)
    print("\n✅ 登录成功，session 已缓存。")


def cmd_verify(args):
    """验证2FA验证码"""
    if not args:
        print("用法: python icloud_tool.py verify <6位验证码>")
        sys.exit(1)

    code = args[0].strip()
    if len(code) != 6 or not code.isdigit():
        print(f"❌ 验证码格式错误: '{code}'，需要 6 位数字")
        sys.exit(1)

    china = os.environ.get('icloud_china') == '1'
    username = os.environ.get('ICLOUD_USERNAME')
    password = os.environ.get('ICLOUD_PASSWORD')

    if not username or not password:
        print("❌ 未设置 ICLOUD_USERNAME 和 ICLOUD_PASSWORD 环境变量")
        sys.exit(1)

    print(f'🍎 正在连接 iCloud{"(中国大陆)" if china else ""}...')
    api = PyiCloudService(username, password, china_mainland=china)

    if not api.requires_2fa:
        print("✅ 不需要双重认证，已直接连接!")
        _verify_all_services(api)
        return

    print(f"🔐 正在验证: {code}")
    if not api.validate_2fa_code(code):
        print("❌ 验证码错误!")
        sys.exit(1)

    print("✅ 验证成功!")
    if not api.is_trusted_session:
        api.trust_session()
        print("✅ 已信任此设备会话")

    # 关键：重新认证以刷新所有 service endpoints（照片、Drive 等）
    print("🔄 正在初始化所有 iCloud 服务...")
    try:
        api.authenticate(force_refresh=True)
    except Exception as e:
        print(f"⚠️ 服务初始化警告: {e}")

    _verify_all_services(api)
    print("\n✅ 登录完成，session 已缓存。后续操作无需再输入密码。")


def _verify_all_services(api):
    """验证所有 iCloud 服务是否可用"""
    services = []

    # 设备
    try:
        devices = list(api.devices)
        services.append(f"📱 设备 ({len(devices)} 个)")
        for d in devices:
            s = d.status()
            print(f'  - {s.get("name", d)} ({s.get("deviceDisplayName", "?")})')
    except Exception as e:
        services.append(f"📱 设备 ❌ {e}")

    # Drive
    try:
        items = list(api.drive.dir())
        services.append(f"💾 iCloud Drive ({len(items)} 个根目录项)")
    except Exception as e:
        services.append(f"💾 iCloud Drive ❌ {e}")

    # 照片
    try:
        albums = list(api.photos.albums)
        services.append(f"📷 照片 ({len(albums)} 个相册)")
    except Exception as e:
        services.append(f"📷 照片 ❌ {e}")

    print("\n📋 服务状态:")
    for s in services:
        print(f"  {s}")


# ─── 照片 ─────────────────────────────────────────────

def cmd_photos(api, args):
    """照片命令"""
    photos = api.photos

    if not args or args[0] == 'albums':
        print('📷 相册列表:')
        for name in photos.albums:
            print(f'  📁 {name}')
        print(f'\n共 {len(photos.albums)} 个相册')

    elif args[0] == 'list':
        limit = int(args[1]) if len(args) > 1 else 10
        library = photos.albums['Library']
        print(f'📷 最近 {limit} 张照片（按时间从新到旧）:\n')
        collected = []
        for i, p in enumerate(library.photos):
            if i >= limit:
                break
            collected.append(p)
            print(f'  {i+1:3}. {p.filename:25} | {p.created}')
        if collected:
            newest = collected[0].created
            oldest = collected[-1].created
            print(f'\n  时间范围: {oldest} ~ {newest}')
            print(f'  ⚠️ 如果显示的是很久以前的照片，说明 session 可能有问题，请重新登录')

    elif args[0] == 'download':
        if len(args) < 2:
            print("用法: photos download <编号>")
            return
        index = int(args[1]) - 1
        library = photos.albums['Library']
        for i, p in enumerate(library.photos):
            if i == index:
                print(f'⬇️  正在下载: {p.filename}')
                dl = p.download()
                with open(p.filename, 'wb') as f:
                    f.write(dl.raw.read())
                size = os.path.getsize(p.filename) / 1024
                print(f'✅ 已保存: {p.filename} ({size:.1f} KB)')
                break
        else:
            print(f'❌ 未找到第 {index+1} 张照片')

    else:
        print(f"未知子命令: {args[0]}")
        print("可用: albums, list [N], download N")


# ─── iCloud Drive ──────────────────────────────────────

def _resolve_drive_path(drive, path_str):
    """解析 iCloud Drive 路径，支持 / 分隔的多级路径。"""
    node = drive
    parts = [p for p in path_str.split('/') if p]
    for part in parts:
        try:
            node = node[part]
        except (KeyError, IndexError):
            print(f"❌ 路径不存在: '{part}'（在 '{path_str}' 中）")
            sys.exit(1)
    return node


def _format_size(size_bytes):
    """格式化文件大小"""
    if size_bytes is None:
        return ""
    if size_bytes > 1024 * 1024:
        return f"{size_bytes / 1024 / 1024:.1f} MB"
    elif size_bytes > 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def _list_node(node, label=""):
    """列出 Drive 节点内容"""
    if label:
        print(f'📂 {label}:\n')
    else:
        print('💾 iCloud Drive:\n')

    items = list(node.dir())
    for item_name in items:
        child = node[item_name]
        # 用 type 属性判断（pyicloud DriveNode 有 type 属性: 'file' or 'folder'）
        node_type = getattr(child, 'type', None)
        if node_type == 'folder':
            print(f'  📂 {item_name}/')
        else:
            size = getattr(child, 'size', None)
            size_str = f"  ({_format_size(size)})" if size else ""
            print(f'  📄 {item_name}{size_str}')
    print(f'\n共 {len(items)} 个项目')


def cmd_drive(api, args):
    """iCloud Drive 命令"""
    from shutil import copyfileobj
    drive = api.drive

    if not args or args[0] == 'list':
        if len(args) > 1:
            path = args[1]
            node = _resolve_drive_path(drive, path)
            _list_node(node, path)
        else:
            _list_node(drive)

    elif args[0] == 'cd' and len(args) > 1:
        path = args[1]
        node = _resolve_drive_path(drive, path)
        _list_node(node, path)

    elif args[0] == 'download' and len(args) > 1:
        path = args[1]
        node = _resolve_drive_path(drive, path)
        filename = path.split('/')[-1]
        output = args[2] if len(args) > 2 else filename

        print(f'⬇️  正在下载: {path}')
        with node.open(stream=True) as response:
            with open(output, 'wb') as f:
                copyfileobj(response.raw, f)
        print(f'✅ 已保存: {output} ({_format_size(os.path.getsize(output))})')

    elif args[0] == 'cat' and len(args) > 1:
        path = args[1]
        node = _resolve_drive_path(drive, path)
        print(f'📄 {path}:\n')
        response = node.open()
        try:
            text = response.content.decode('utf-8')
            print(text)
        except UnicodeDecodeError:
            print("⚠️ 文件不是文本格式，请用 download 命令下载")

    elif args[0] == 'upload' and len(args) > 1:
        local_file = args[1]
        target_folder = args[2] if len(args) > 2 else None
        if not os.path.exists(local_file):
            print(f"❌ 本地文件不存在: {local_file}")
            return
        folder_node = _resolve_drive_path(drive, target_folder) if target_folder else drive
        filename = os.path.basename(local_file)
        print(f'⬆️  正在上传: {filename} → iCloud Drive/{target_folder or ""}')
        with open(local_file, 'rb') as f:
            folder_node.upload(f)
        print(f'✅ 上传完成: {filename}')

    elif args[0] == 'mkdir' and len(args) > 1:
        # mkdir Work/新文件夹 → 在 Work 下创建 "新文件夹"
        path = args[1]
        parts = [p for p in path.split('/') if p]
        new_name = parts[-1]
        parent_path = '/'.join(parts[:-1]) if len(parts) > 1 else None
        parent = _resolve_drive_path(drive, parent_path) if parent_path else drive
        parent.mkdir(new_name)
        print(f'✅ 已创建文件夹: {path}')

    elif args[0] == 'rename' and len(args) > 2:
        path = args[1]
        new_name = args[2]
        node = _resolve_drive_path(drive, path)
        node.rename(new_name)
        print(f'✅ 已重命名: {path} → {new_name}')

    elif args[0] == 'delete' and len(args) > 1:
        path = args[1]
        node = _resolve_drive_path(drive, path)
        node.delete()
        print(f'🗑️ 已删除: {path}')

    else:
        sub = args[0] if args else '(空)'
        print(f"未知子命令: {sub}")
        print("可用: list [路径], cd <路径>, download <路径> [输出], cat <路径>,")
        print("      upload <本地文件> [目标文件夹], mkdir <路径>, rename <路径> <新名>, delete <路径>")


# ─── 设备 / 查找 ───────────────────────────────────────

def _get_device(api, identifier=None):
    """获取设备。支持按编号(1-based)、名称片段、或设备ID"""
    devices = list(api.devices)
    if not devices:
        print("❌ 没有找到任何设备")
        sys.exit(1)

    if identifier is None:
        # 默认返回第一个 iPhone，找不到就返回第一个设备
        for d in devices:
            status = d.status()
            if 'iPhone' in status.get('deviceDisplayName', ''):
                return d
        return devices[0]

    # 按编号
    if identifier.isdigit():
        idx = int(identifier) - 1
        if 0 <= idx < len(devices):
            return devices[idx]
        print(f"❌ 设备编号超出范围 (1-{len(devices)})")
        sys.exit(1)

    # 按名称片段匹配
    for d in devices:
        status = d.status()
        name = status.get('name', '')
        display = status.get('deviceDisplayName', '')
        if identifier.lower() in name.lower() or identifier.lower() in display.lower():
            return d

    print(f"❌ 未找到匹配 '{identifier}' 的设备")
    print("可用设备:")
    for i, d in enumerate(devices):
        s = d.status()
        print(f"  {i+1}. {s.get('name', '?')} ({s.get('deviceDisplayName', '?')})")
    sys.exit(1)


def cmd_devices(api, args):
    """设备列表 — 显示详细信息"""
    print('📱 我的设备:\n')
    devices = list(api.devices)
    for i, d in enumerate(devices):
        try:
            s = d.status()
            name = s.get('name', '未知')
            model = s.get('deviceDisplayName', '?')
            battery = s.get('batteryLevel')
            battery_str = f"  🔋 {battery*100:.0f}%" if battery and battery > 0 else ""
            status = s.get('deviceStatus', '?')
            print(f'  {i+1}. {name} ({model}){battery_str}  [status: {status}]')
        except Exception:
            print(f'  {i+1}. {d}')
    print(f'\n共 {len(devices)} 个设备')


def cmd_find(api, args):
    """查找设备命令 — 定位、状态、播放声音、丢失模式"""
    if not args:
        print("用法: find <子命令> [设备]")
        print("  locate [设备]          获取设备位置")
        print("  status [设备]          获取设备详细状态")
        print("  play [设备]            播放声音（找手机）")
        print("  lost <电话> <消息> [设备]  启用丢失模式")
        print("\n[设备] 可以是编号(1,2,3)、名称片段(iPhone)、或省略(默认 iPhone)")
        return

    subcmd = args[0]

    if subcmd == 'locate':
        device = _get_device(api, args[1] if len(args) > 1 else None)
        s = device.status()
        print(f'📍 正在定位: {s.get("name", "?")}...\n')
        loc = device.location
        if loc:
            lat = loc.get('latitude', '?')
            lng = loc.get('longitude', '?')
            acc = loc.get('horizontalAccuracy', '?')
            pos_type = loc.get('positionType', '?')
            ts = loc.get('timeStamp')
            time_str = ""
            if ts:
                try:
                    time_str = f"  ⏰ {datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')}"
                except Exception:
                    pass
            print(f'  纬度: {lat}')
            print(f'  经度: {lng}')
            print(f'  精度: {acc}m ({pos_type}){time_str}')
            print(f'\n  🗺️  地图: https://maps.apple.com/?ll={lat},{lng}')
        else:
            print("  ❌ 无法获取位置（设备可能离线）")

    elif subcmd == 'status':
        device = _get_device(api, args[1] if len(args) > 1 else None)
        s = device.status()
        print(f'📱 设备状态:\n')
        print(f'  名称: {s.get("name", "?")}')
        print(f'  型号: {s.get("deviceDisplayName", "?")}')
        print(f'  类型: {s.get("deviceClass", "?")}')
        battery = s.get('batteryLevel')
        if battery and battery > 0:
            print(f'  电量: {battery*100:.0f}%')
        bat_status = s.get('batteryStatus', '')
        if bat_status:
            status_map = {'Charging': '充电中', 'NotCharging': '未充电', 'Charged': '已充满'}
            print(f'  充电: {status_map.get(bat_status, bat_status)}')
        print(f'  状态码: {s.get("deviceStatus", "?")}')
        loc = device.location
        if loc and loc.get('latitude'):
            old = "⚠️ 旧位置" if loc.get('isOld') else "最新"
            print(f'  位置: {loc["latitude"]:.6f}, {loc["longitude"]:.6f} ({old})')

    elif subcmd == 'play':
        device = _get_device(api, args[1] if len(args) > 1 else None)
        s = device.status()
        name = s.get('name', '?')
        print(f'🔊 正在向 {name} 发送声音...')
        device.play_sound()
        print(f'✅ 已发送！{name} 会响铃并显示通知。')

    elif subcmd == 'lost':
        if len(args) < 3:
            print("用法: find lost <电话号码> <显示消息> [设备]")
            print("  示例: find lost 13800138000 \"请联系我归还手机\"")
            return
        phone = args[1]
        message = args[2]
        device = _get_device(api, args[3] if len(args) > 3 else None)
        s = device.status()
        name = s.get('name', '?')
        print(f'🔒 正在对 {name} 启用丢失模式...')
        print(f'   联系电话: {phone}')
        print(f'   显示消息: {message}')
        device.lost_device(phone, message)
        print(f'✅ 丢失模式已启用！设备会锁定并显示联系信息。')

    else:
        print(f"未知子命令: {subcmd}")
        print("可用: locate, status, play, lost")


# ─── 帮助 & 主入口 ─────────────────────────────────────

def show_help():
    print("""
🍎 Apple iCloud 命令行工具（非交互式，适配 AI 环境）

用法: python icloud_tool.py <命令> [参数]

认证:
  login                      登录（如需2FA会提示并退出，退出码 2）
  verify <验证码>             输入 6 位 2FA 验证码完成登录

照片:
  photos albums              列出所有相册
  photos list [N]            列出最近 N 张照片 (默认 10)
  photos download N          下载第 N 张照片

iCloud Drive:
  drive list [路径]          列出目录（支持多级路径如 Work/Docs）
  drive cd <路径>            进入并列出文件夹
  drive download <路径> [输出]  下载文件
  drive cat <路径>           查看文本文件内容
  drive upload <本地文件> [目标]  上传文件
  drive mkdir <路径>         创建文件夹
  drive rename <路径> <新名>  重命名文件/文件夹
  drive delete <路径>        删除文件/文件夹

设备:
  devices                    列出所有设备（含型号、电量）

查找设备 (Find My):
  find locate [设备]         获取设备 GPS 位置
  find status [设备]         获取设备详细状态
  find play [设备]           播放声音（找手机）
  find lost <电话> <消息> [设备]  启用丢失模式

  [设备] = 编号(1,2,3) / 名称片段(iPhone) / 省略(默认iPhone)

环境变量:
  ICLOUD_USERNAME            Apple ID 邮箱
  ICLOUD_PASSWORD            主密码 (不是应用专用密码)
  ICLOUD_CHINA               设为 1 表示中国大陆 (默认 1)
""")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        show_help()
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == 'login':
        cmd_login()
        return
    elif cmd == 'verify':
        cmd_verify(args)
        return

    api = get_api()

    if cmd == 'photos':
        cmd_photos(api, args)
    elif cmd == 'drive':
        cmd_drive(api, args)
    elif cmd == 'devices':
        cmd_devices(api, args)
    elif cmd == 'find':
        cmd_find(api, args)
    else:
        print(f'❌ 未知命令: {cmd}')
        print('运行 python icloud_tool.py --help 查看帮助')


if __name__ == '__main__':
    main()
