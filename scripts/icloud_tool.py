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
  python icloud_tool.py [photos|drive|devices] [子命令]

环境变量:
  ICLOUD_USERNAME  - Apple ID
  ICLOUD_PASSWORD  - 主密码 (非应用专用密码)
  ICLOUD_CHINA     - 设为 1 表示中国大陆用户（默认 1）
"""

import sys
import os

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


def get_api(require_password=False):
    """
    连接 iCloud — 优先 session，fallback 到密码。
    全程非交互式，所有输入通过环境变量或命令行参数。

    参数:
      require_password: True 时跳过 session 缓存，直接用密码登录（用于 login 命令）
    """
    china = os.environ.get('icloud_china') == '1'
    username = os.environ.get('ICLOUD_USERNAME')
    password = os.environ.get('ICLOUD_PASSWORD')

    # 方式 1：尝试 session 缓存（免密）
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

    # 方式 2：通过密码登录
    if not username:
        print("❌ 未设置 ICLOUD_USERNAME 环境变量")
        sys.exit(1)
    if not password:
        print("❌ 未设置 ICLOUD_PASSWORD 环境变量")
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
    """登录命令 — 通过环境变量登录，如需2FA则提示并退出"""
    api = get_api(require_password=True)
    # 如果走到这里说明不需要 2FA，直接成功
    try:
        devices = list(api.devices)
        print(f"📱 检测到 {len(devices)} 个设备")
        for d in devices:
            print(f'  - {d}')
    except Exception:
        pass
    print("\n✅ 登录成功，session 已缓存。")


def cmd_verify(args):
    """验证2FA验证码 — 完成登录"""
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
        return

    print(f"🔐 正在验证: {code}")
    if not api.validate_2fa_code(code):
        print("❌ 验证码错误!")
        sys.exit(1)

    print("✅ 验证成功!")

    if not api.is_trusted_session:
        api.trust_session()
        print("✅ 已信任此设备会话")

    try:
        devices = list(api.devices)
        print(f"\n📱 检测到 {len(devices)} 个设备:")
        for d in devices:
            print(f'  - {d}')
    except Exception:
        pass

    print("\n✅ 登录完成，session 已缓存。后续操作无需再输入密码。")


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
        print(f'📷 最近 {limit} 张照片:\n')
        for i, p in enumerate(library.photos):
            if i >= limit:
                break
            print(f'  {i+1:3}. {p.filename:25} | {p.created}')

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


def _resolve_drive_path(drive, path_str):
    """
    解析 iCloud Drive 路径，支持 / 分隔的多级路径。
    例如: "Work/Projects/doc.txt" → drive['Work']['Projects']['doc.txt']
    """
    node = drive
    parts = [p for p in path_str.split('/') if p]
    for part in parts:
        try:
            node = node[part]
        except (KeyError, IndexError):
            print(f"❌ 路径不存在: '{part}'（在 '{path_str}' 中）")
            sys.exit(1)
    return node


def _list_node(node, label=""):
    """列出一个 Drive 节点的内容"""
    if label:
        print(f'📂 {label}:\n')
    else:
        print('💾 iCloud Drive:\n')

    items = list(node.dir())
    for item_name in items:
        child = node[item_name]
        # 判断是文件还是文件夹
        if hasattr(child, 'dir') and callable(child.dir):
            try:
                child.dir()
                print(f'  📂 {item_name}/')
            except Exception:
                # 是文件
                size = getattr(child, 'size', None)
                size_str = f" ({size:,} bytes)" if size else ""
                print(f'  📄 {item_name}{size_str}')
        else:
            print(f'  📄 {item_name}')
    print(f'\n共 {len(items)} 个项目')


def cmd_drive(api, args):
    """iCloud Drive 命令"""
    from shutil import copyfileobj
    drive = api.drive

    if not args or args[0] == 'list':
        # list [路径]
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

        # 可选指定输出路径
        output = args[2] if len(args) > 2 else filename

        print(f'⬇️  正在下载: {path}')
        with node.open(stream=True) as response:
            with open(output, 'wb') as f:
                copyfileobj(response.raw, f)

        size = os.path.getsize(output)
        if size > 1024 * 1024:
            size_str = f"{size / 1024 / 1024:.1f} MB"
        elif size > 1024:
            size_str = f"{size / 1024:.1f} KB"
        else:
            size_str = f"{size} bytes"
        print(f'✅ 已保存: {output} ({size_str})')

    elif args[0] == 'cat' and len(args) > 1:
        path = args[1]
        node = _resolve_drive_path(drive, path)

        print(f'📄 {path}:\n')
        response = node.open()
        # 尝试文本输出
        try:
            text = response.content.decode('utf-8')
            print(text)
        except UnicodeDecodeError:
            print(f"⚠️ 文件不是文本格式，请用 download 命令下载")

    elif args[0] == 'upload' and len(args) > 1:
        local_file = args[1]
        # 可选指定目标文件夹路径
        target_folder = args[2] if len(args) > 2 else None

        if not os.path.exists(local_file):
            print(f"❌ 本地文件不存在: {local_file}")
            return

        if target_folder:
            folder_node = _resolve_drive_path(drive, target_folder)
        else:
            folder_node = drive

        filename = os.path.basename(local_file)
        print(f'⬆️  正在上传: {local_file} → iCloud Drive/{target_folder or ""}/{filename}')

        with open(local_file, 'rb') as f:
            folder_node.upload(f)

        print(f'✅ 上传完成: {filename}')

    else:
        print(f"未知子命令: {args[0] if args else '(空)'}")
        print("可用: list [路径], cd <路径>, download <路径> [输出文件], cat <路径>, upload <本地文件> [目标文件夹]")


def cmd_devices(api, args):
    """设备命令"""
    print('📱 我的设备:\n')
    devices = list(api.devices)
    for d in devices:
        print(f'  - {d}')
    print(f'\n共 {len(devices)} 个设备')


def show_help():
    """显示帮助"""
    print("""
🍎 Apple iCloud 命令行工具（非交互式，适配 AI 环境）

用法: python icloud_tool.py <命令> [参数]

认证命令:
  login                  登录（如需2FA会提示并退出，退出码 2）
  verify <验证码>         输入 6 位 2FA 验证码完成登录

功能命令:
  photos                 照片功能
    albums               列出所有相册
    list [N]             列出最近 N 张照片 (默认 10)
    download N           下载第 N 张照片

  drive                  iCloud Drive 功能
    list [路径]          列出目录内容（支持多级路径如 Work/Docs）
    cd <路径>            进入并列出文件夹内容
    download <路径> [输出] 下载文件到本地
    cat <路径>           查看文本文件内容
    upload <本地文件> [目标文件夹]  上传文件

  devices                列出所有设备

认证方式 (按优先级):
  1. 已缓存的 session
  2. 环境变量 ICLOUD_USERNAME + ICLOUD_PASSWORD

环境变量:
  ICLOUD_USERNAME        Apple ID 邮箱
  ICLOUD_PASSWORD        主密码 (不是应用专用密码)
  ICLOUD_CHINA           设为 1 表示中国大陆 (默认 1)
""")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        show_help()
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    # 认证命令（不需要先 get_api）
    if cmd == 'login':
        cmd_login()
        return
    elif cmd == 'verify':
        cmd_verify(args)
        return

    # 功能命令（需要先连接）
    api = get_api()

    if cmd == 'photos':
        cmd_photos(api, args)
    elif cmd == 'drive':
        cmd_drive(api, args)
    elif cmd == 'devices':
        cmd_devices(api, args)
    else:
        print(f'❌ 未知命令: {cmd}')
        print('运行 python icloud_tool.py --help 查看帮助')


if __name__ == '__main__':
    main()
