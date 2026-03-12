#!/usr/bin/env python3
"""
iCloud 日历工具 (CalDAV 方式)
使用 caldav 库直接访问 iCloud 日历，需要应用专用密码

用法: python icloud_calendar.py [list|today|week|new|search|delete] [参数]

环境变量:
  ICLOUD_USERNAME     - Apple ID
  ICLOUD_APP_PASSWORD - 应用专用密码 (在 appleid.apple.com 生成)

注意: 日历功能使用 CalDAV 协议，需要应用专用密码（不是主密码）
"""

import sys
import os
from datetime import datetime, timedelta, date
import re
import argparse

try:
    import caldav
except ImportError:
    print("请先安装 caldav: pip install caldav")
    sys.exit(1)

try:
    from icalendar import Calendar, Event
except ImportError:
    print("请先安装 icalendar: pip install icalendar")
    sys.exit(1)


# iCloud CalDAV URL
CALDAV_URL = "https://caldav.icloud.com/"


def get_client():
    """获取 CalDAV 客户端连接"""
    username = os.environ.get('ICLOUD_USERNAME')
    app_password = os.environ.get('ICLOUD_APP_PASSWORD')
    
    if not username:
        print("❌ 未设置 ICLOUD_USERNAME 环境变量！")
        print("   export ICLOUD_USERNAME=\"你的Apple ID邮箱\"")
        sys.exit(1)
    if not app_password:
        print("❌ 未设置 ICLOUD_APP_PASSWORD 环境变量！")
        print("\n⚠️  日历功能需要应用专用密码（非主密码）")
        print("   1. 登录 https://appleid.apple.com")
        print("   2. 进入「登录与安全」→「应用专用密码」→「+」")
        print("   3. 生成后设置环境变量:")
        print("      export ICLOUD_APP_PASSWORD=\"xxxx-xxxx-xxxx-xxxx\"")
        sys.exit(1)
    
    print(f'📅 正在连接 iCloud 日历...')
    
    try:
        client = caldav.DAVClient(
            url=CALDAV_URL,
            username=username,
            password=app_password
        )
        
        # 测试连接
        principal = client.principal()
        print("✅ 已连接!\n")
        return client, principal
        
    except caldav.lib.error.AuthorizationError:
        print("❌ 认证失败!")
        print("\n可能的原因:")
        print("  1. 应用专用密码不正确")
        print("  2. 应用专用密码已过期")
        print("  3. Apple ID 不正确")
        print("\n请在 https://appleid.apple.com 重新生成应用专用密码")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)


def get_calendars(principal):
    """获取所有日历"""
    calendars = principal.calendars()
    return calendars


def list_calendars(principal):
    """列出所有日历"""
    print("📅 日历列表:\n")
    calendars = get_calendars(principal)
    
    for i, cal in enumerate(calendars, 1):
        name = cal.name or "未命名"
        print(f"  {i}. 📁 {name}")
    
    print(f"\n共 {len(calendars)} 个日历")
    return calendars


def parse_event(event):
    """解析事件信息"""
    try:
        ical = Calendar.from_ical(event.data)
        for component in ical.walk():
            if component.name == "VEVENT":
                summary = str(component.get('summary', '未命名'))
                dtstart = component.get('dtstart')
                dtend = component.get('dtend')
                location = str(component.get('location', '')) or None
                description = str(component.get('description', '')) or None
                
                # 处理日期时间
                start_dt = dtstart.dt if dtstart else None
                end_dt = dtend.dt if dtend else None
                
                # 判断是否全天事件
                all_day = not hasattr(start_dt, 'hour') if start_dt else False
                
                return {
                    'summary': summary,
                    'start': start_dt,
                    'end': end_dt,
                    'location': location,
                    'description': description,
                    'all_day': all_day
                }
    except Exception as e:
        return None
    return None


def format_event(event_info):
    """格式化事件显示"""
    if not event_info:
        return "  (无法解析)"
    
    summary = event_info['summary']
    start = event_info['start']
    end = event_info['end']
    location = event_info['location']
    all_day = event_info['all_day']
    
    if all_day:
        if hasattr(start, 'strftime'):
            date_str = start.strftime("%Y-%m-%d")
        else:
            date_str = str(start)
        time_str = "全天"
    else:
        if hasattr(start, 'strftime'):
            date_str = start.strftime("%Y-%m-%d")
            start_time = start.strftime("%H:%M")
            end_time = end.strftime("%H:%M") if end and hasattr(end, 'strftime') else ""
            time_str = f"{start_time}-{end_time}" if end_time else start_time
        else:
            date_str = str(start)[:10] if start else "未知"
            time_str = ""
    
    result = f"  📌 {summary}"
    result += f"\n     📆 {date_str} {time_str}"
    if location:
        result += f"\n     📍 {location}"
    
    return result


def list_events(principal, start_date=None, end_date=None, calendar_name=None):
    """列出事件"""
    if start_date is None:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if end_date is None:
        end_date = start_date + timedelta(days=1)
    
    calendars = get_calendars(principal)
    
    # 筛选日历
    if calendar_name:
        calendars = [c for c in calendars if calendar_name.lower() in (c.name or '').lower()]
        if not calendars:
            print(f"❌ 未找到日历: {calendar_name}")
            return
    
    all_events = []
    
    for cal in calendars:
        try:
            events = cal.search(start=start_date, end=end_date, event=True, expand=True)
            for event in events:
                event_info = parse_event(event)
                if event_info:
                    event_info['calendar'] = cal.name
                    all_events.append(event_info)
        except Exception as e:
            pass
    
    # 按时间排序 (统一 date/datetime/timezone 类型)
    def _sort_key(ev):
        s = ev['start']
        if s is None:
            return datetime.max.timestamp()
        if isinstance(s, datetime):
            try:
                return s.timestamp()
            except Exception:
                return s.replace(tzinfo=None).timestamp() if hasattr(s, 'replace') else 0
        if isinstance(s, date):
            return datetime.combine(s, datetime.min.time()).timestamp()
        return 0

    all_events.sort(key=_sort_key)
    
    return all_events


def cmd_list(principal, args):
    """列出日历"""
    list_calendars(principal)


def cmd_today(principal, args):
    """显示今天的事件"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    print(f"📅 今天的事件 ({today.strftime('%Y-%m-%d')}):\n")
    
    events = list_events(principal, today, tomorrow)
    
    if not events:
        print("  没有事件")
    else:
        for event in events:
            print(format_event(event))
            print()
    
    print(f"共 {len(events)} 个事件")


def cmd_week(principal, args):
    """显示本周事件"""
    days = int(args[0]) if args else 7
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + timedelta(days=days)
    
    print(f"📅 未来 {days} 天的事件:\n")
    
    events = list_events(principal, today, end_date)
    
    if not events:
        print("  没有事件")
    else:
        current_date = None
        for event in events:
            event_date = event['start']
            if hasattr(event_date, 'date'):
                event_date = event_date.date()
            elif hasattr(event_date, 'strftime'):
                pass
            else:
                event_date = None
            
            # 按日期分组显示
            if event_date != current_date:
                current_date = event_date
                if hasattr(current_date, 'strftime'):
                    print(f"\n--- {current_date.strftime('%Y-%m-%d %A')} ---")
                else:
                    print(f"\n--- {current_date} ---")
            
            print(format_event(event))
    
    print(f"\n共 {len(events)} 个事件")


def find_calendar(principal, calendar_name):
    """按名称查找日历"""
    calendars = get_calendars(principal)
    for c in calendars:
        if (c.name or '').strip() == calendar_name.strip():
            return c
    # 模糊匹配
    for c in calendars:
        if calendar_name.lower() in (c.name or '').lower():
            return c
    return None


def cmd_new(principal, args):
    """创建新事件，支持 --calendar, --location, --description"""
    parser = argparse.ArgumentParser(prog='new', add_help=False)
    parser.add_argument('date_str')
    parser.add_argument('rest', nargs='*')
    parser.add_argument('--calendar', '-c', default=None)
    parser.add_argument('--location', '-l', default=None)
    parser.add_argument('--description', '-d', default=None)

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print("用法: new <日期> [开始时间 [结束时间]] <标题> [--calendar 日历名] [--location 地点] [--description 描述]")
        print("示例: new 2026-02-10 10:00 11:00 \"开会\" --calendar \"个人\"")
        print("      new today \"📦 取快递\" --calendar \"家庭看板\"")
        return

    date_str = parsed.date_str
    rest = parsed.rest

    if not rest:
        print("❌ 缺少标题")
        print("用法: new <日期> [开始时间 [结束时间]] <标题> [--calendar 名称]")
        return

    # 判断参数模式: rest 可能是 [title] / [start, title] / [start, end, title]
    time_pattern = re.compile(r'^\d{1,2}:\d{2}$')

    if len(rest) >= 3 and time_pattern.match(rest[0]) and time_pattern.match(rest[1]):
        start_time = rest[0]
        end_time = rest[1]
        title = ' '.join(rest[2:])
    elif len(rest) >= 2 and time_pattern.match(rest[0]):
        start_time = rest[0]
        end_time = None
        title = ' '.join(rest[1:])
    else:
        start_time = None
        end_time = None
        title = ' '.join(rest)

    # 解析日期
    try:
        if date_str == 'today':
            event_date = datetime.now().date()
        elif date_str == 'tomorrow':
            event_date = (datetime.now() + timedelta(days=1)).date()
        else:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        print(f"❌ 日期格式错误: {date_str}")
        print("   请使用 YYYY-MM-DD 格式，如 2026-02-10")
        return

    # 选择日历
    if parsed.calendar:
        cal = find_calendar(principal, parsed.calendar)
        if not cal:
            print(f"❌ 未找到日历: {parsed.calendar}")
            print("可用日历:")
            for c in get_calendars(principal):
                print(f"  - {c.name}")
            return
    else:
        calendars = get_calendars(principal)
        if not calendars:
            print("❌ 没有可用的日历")
            return
        cal = calendars[0]

    # 创建事件
    from icalendar import Calendar as ICalendar, Event as IEvent
    import uuid

    ical = ICalendar()
    ical.add('prodid', '-//iCloud Calendar Tool//EN')
    ical.add('version', '2.0')

    event = IEvent()
    event.add('summary', title)
    event.add('uid', str(uuid.uuid4()))
    event.add('dtstamp', datetime.now())

    if parsed.location:
        event.add('location', parsed.location)
    if parsed.description:
        event.add('description', parsed.description)

    if start_time:
        start_dt = datetime.combine(event_date, datetime.strptime(start_time, "%H:%M").time())
        event.add('dtstart', start_dt)
        if end_time:
            end_dt = datetime.combine(event_date, datetime.strptime(end_time, "%H:%M").time())
            event.add('dtend', end_dt)
    else:
        event.add('dtstart', event_date)
        event.add('dtend', event_date + timedelta(days=1))

    ical.add_component(event)

    try:
        cal.save_event(ical.to_ical().decode('utf-8'))
        print(f"✅ 事件已创建: {title}")
        print(f"   日期: {event_date}")
        if start_time:
            print(f"   时间: {start_time}-{end_time or ''}")
        else:
            print(f"   类型: 全天事件")
        print(f"   日历: {cal.name}")
        if parsed.location:
            print(f"   地点: {parsed.location}")
        if parsed.description:
            print(f"   描述: {parsed.description}")
    except Exception as e:
        print(f"❌ 创建失败: {e}")


def cmd_search(principal, args):
    """搜索事件，支持 --calendar"""
    parser = argparse.ArgumentParser(prog='search', add_help=False)
    parser.add_argument('keywords', nargs='*')
    parser.add_argument('--calendar', '-c', default=None)
    parser.add_argument('--days', type=int, default=30)

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print("用法: search <关键词> [--calendar 日历名] [--days N]")
        return

    if not parsed.keywords:
        print("用法: search <关键词> [--calendar 日历名]")
        return

    keyword = ' '.join(parsed.keywords).lower()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + timedelta(days=parsed.days)

    print(f"🔍 搜索: {keyword}" + (f" (日历: {parsed.calendar})" if parsed.calendar else "") + "\n")

    events = list_events(principal, today, end_date, calendar_name=parsed.calendar)

    if events is None:
        return

    matched = []
    for event in events:
        if keyword in event['summary'].lower():
            matched.append(event)
        elif event['location'] and keyword in event['location'].lower():
            matched.append(event)
        elif event['description'] and keyword in event['description'].lower():
            matched.append(event)

    if not matched:
        print("  没有找到匹配的事件")
    else:
        for event in matched:
            print(format_event(event))
            print()

    print(f"找到 {len(matched)} 个事件")


def cmd_delete(principal, args):
    """删除事件，按关键词匹配删除"""
    parser = argparse.ArgumentParser(prog='delete', add_help=False)
    parser.add_argument('keywords', nargs='*')
    parser.add_argument('--calendar', '-c', default=None)
    parser.add_argument('--days', type=int, default=30)

    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        print("用法: delete <关键词> [--calendar 日历名]")
        return

    if not parsed.keywords:
        print("用法: delete <关键词> [--calendar 日历名]")
        return

    keyword = ' '.join(parsed.keywords).lower()

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = today + timedelta(days=parsed.days)

    # 获取目标日历
    calendars = get_calendars(principal)
    if parsed.calendar:
        calendars = [c for c in calendars if parsed.calendar.lower() in (c.name or '').lower()]
        if not calendars:
            print(f"❌ 未找到日历: {parsed.calendar}")
            return

    deleted = 0
    for cal in calendars:
        try:
            events = cal.search(start=today, end=end_date, event=True, expand=False)
            for event in events:
                event_info = parse_event(event)
                if event_info and keyword in event_info['summary'].lower():
                    print(f"  🗑️  删除: {event_info['summary']}")
                    event.delete()
                    deleted += 1
        except Exception as e:
            pass

    print(f"\n共删除 {deleted} 个事件")


def show_help():
    """显示帮助"""
    print("""
📅 iCloud 日历工具 (CalDAV)

用法: python icloud_calendar.py <命令> [参数]

命令:
  list                   列出所有日历
  today                  显示今天的事件
  week [N]               显示未来 N 天的事件 (默认 7)
  new <日期> [时间] <标题> [选项]  创建新事件
  search <关键词> [选项]  搜索事件
  delete <关键词> [选项]  删除匹配的事件

创建事件示例:
  new 2026-02-10 10:00 11:00 "开会"                        # 指定时间
  new 2026-02-10 "生日"                                     # 全天事件
  new today "📦 取快递" --calendar "家庭看板"                # 指定日历
  new 2026-03-20 20:00 22:30 "🎬 封神3" -c "家庭看板" -l "万达影城" -d "G排12座"

搜索/删除示例:
  search 快递 --calendar "家庭看板"
  delete 快递 --calendar "家庭看板"

选项:
  --calendar, -c    指定目标日历名称
  --location, -l    事件地点 (仅 new)
  --description, -d 事件描述 (仅 new)
  --days N          搜索/删除范围天数 (默认 30)

环境变量:
  ICLOUD_USERNAME        Apple ID 邮箱
  ICLOUD_APP_PASSWORD    应用专用密码 (非主密码!)

⚠️  重要: 日历功能需要应用专用密码
   1. 登录 https://appleid.apple.com
   2. 进入「登录与安全」→「应用专用密码」
   3. 点击「+」生成新密码
   4. 复制密码 (格式: xxxx-xxxx-xxxx-xxxx)
""")


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        show_help()
        sys.exit(0)
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    # 日历命令不需要 pyicloud 连接
    client, principal = get_client()
    
    if cmd == 'list':
        cmd_list(principal, args)
    elif cmd == 'today':
        cmd_today(principal, args)
    elif cmd == 'week':
        cmd_week(principal, args)
    elif cmd == 'new':
        cmd_new(principal, args)
    elif cmd == 'search':
        cmd_search(principal, args)
    elif cmd == 'delete':
        cmd_delete(principal, args)
    else:
        print(f'❌ 未知命令: {cmd}')
        print('运行 python icloud_calendar.py --help 查看帮助')


if __name__ == '__main__':
    main()
