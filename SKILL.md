---
name: OpenClaw with Apple
description: Apple iCloud 全功能访问 + Apple Health 深度健康分析
icon: 🍎
os: linux, macos
tools: pyicloud, caldav
install: |
  pip install pyicloud caldav icalendar
---

# OpenClaw with Apple

Apple iCloud 服务访问 + Apple Health 深度健康分析的 AI Skill。

---

## 🎯 Skill 启用引导流程

> **重要**：启用此 Skill 后，请严格按照以下流程与用户交互。

### 第一步：开场 & 收集凭证

Skill 启用后，直接告知用户需要什么、怎么拿：

```
你好！我来帮你配置 OpenClaw with Apple。

我需要以下信息来连接你的 iCloud 服务：

1️⃣ 应用专用密码（必选）— 用于读写日历
   → 获取方式：https://appleid.apple.com →「登录与安全」→「应用专用密码」→ 生成

2️⃣ Apple ID 邮箱 + 主密码（可选）— 用于照片、iCloud Drive、查找设备、Health 健康分析
   → 就是你登录 Apple ID 的邮箱和密码

如果你只需要日历功能，提供应用专用密码即可。
如果还需要照片/文件/设备/健康分析，请同时提供 Apple ID 邮箱和主密码。
```

#### 用户只提供了应用专用密码：

设置环境变量并验证日历：

```bash
export ICLOUD_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
python icloud_calendar.py list    # 验证日历
```

验证成功后：

```
✅ iCloud 日历已配置完成！

你可以直接告诉我你想做什么，比如：
  "帮我查看今天的日历"
  "下周三下午 3 点帮我建个会议"
```

**（流程结束，不再询问其他功能）**

#### 用户提供了邮箱 + 主密码：

AI 直接通过环境变量设置凭证并登录，**全程非交互式**：

```bash
export ICLOUD_USERNAME="用户提供的邮箱"
export ICLOUD_PASSWORD="用户提供的主密码"
python icloud_tool.py login       # 第一步：尝试登录
```

脚本会自动判断是否需要双重认证：
- **不需要 2FA** → 直接登录成功，进入第二步
- **需要 2FA**（退出码 2）→ AI 立刻告知用户：

```
你的 iPhone 上应该收到了一个 6 位验证码弹窗，把验证码发给我。
```

用户发来验证码后，AI 执行：

```bash
python icloud_tool.py verify 123456    # 用验证码完成登录
```

> 认证成功后 session 会被缓存到 `~/.pyicloud/`，后续使用不再需要密码。

验证成功后，进入第二步。

---

### 第二步：询问 Health（仅当用户提供了主密码）

```
✅ Apple iCloud 已配置完成（照片、Drive、设备、日历全部可用）！

你需要启用 Apple Health 健康分析吗？
基于 iPhone 的心率、睡眠、步数、活动能量，给你做深度健康分析和压力评估。
无需任何密码，只需在 iPhone 上导入一个快捷指令。
```

#### 用户不需要 Health：

```
✅ 配置完成！你可以直接告诉我你想做什么，比如：
  "帮我查看今天的日历"
  "看看 iCloud Drive 里有什么"
  "我的设备都在哪"
```

**（流程结束）**

#### 用户需要 Health：

```
🏥 配置 Apple Health：

📱 第 1 步：导入快捷指令

用 iPhone Safari 打开以下链接，点击「添加快捷指令」：
https://www.icloud.com/shortcuts/4a5dff0072a6463a9a1fef47d6ec13e2

⚠️ 必须用 iPhone 打开，电脑上打不开。

🔓 第 2 步：开通健康数据权限

1. 在「快捷指令」App 中找到刚添加的「Health Daily Export」
2. 手动运行一次，系统会逐一弹出权限请求：
   步数 → 允许 | 心率 → 允许 | 睡眠 → 允许 | 活动能量 → 允许
3. 运行成功后会提示保存文件到 iCloud Drive

🔐 第 3 步：开启共享大量数据

iPhone →「设置」→「快捷指令」→「高级」→ 开启「允许共享大量数据」
（不开此选项，自动化运行时可能无法导出数据）

⏰ 第 4 步：设置每日自动化

快捷指令 App → 底部「自动化」→ 右上角 + →「特定时间」→ 每天 23:00 → 运行「Health Daily Export」→ 关闭「运行前询问」

你可以在自动化里调整数据采集时间。设好后告诉我你希望几点收到健康报告（报告时间要晚于采集时间，这样数据才完整）。
```

---

### 第三步：设置健康报告定时推送

用户告知期望的报告时间后（比如「早上 8 点」）：

1. 确认报告时间晚于采集时间（如采集 23:00，报告次日 08:00 ✅）
2. 使用 cron 设置定时任务，自动运行分析并输出报告：

```bash
# 示例：每天早上 8 点分析昨天的健康数据
0 8 * * * cd /path/to/project && python scripts/health_tool.py today
```

设置完成后：

```
✅ 全部配置完成！

  🍎 Apple iCloud — 照片、Drive、设备、日历
  🏥 Apple Health — 每天 {报告时间} 自动推送健康分析报告

快捷指令每天 {采集时间} 自动采集数据，我会在 {报告时间} 为你生成深度分析。
你也可以随时问我：「我最近睡眠怎么样」「分析一下过去一周的数据」
```

---

## 💡 AI 日常行为规则

### Health 相关

1. **定时报告**：在用户设定的报告时间，自动读取 iCloud Drive 中最新的健康数据文件并生成深度分析
2. **文件路径**：`~/Library/Mobile Documents/com~apple~CloudDocs/Shortcuts/Health/health_YYYY-MM-DD.txt`
3. **分析命令**：`python scripts/health_tool.py analyze <file>` 或 `python scripts/health_tool.py today`
4. **用户主动询问**：随时可以问健康相关问题，AI 自动读取对应日期的数据分析
5. **多日趋势**：`python scripts/health_tool.py report <dir> --days 7`

### iCloud 相关

1. 用户提到日历、照片、文件、设备时，直接调用对应工具执行
2. iCloud session 过期时，告知用户 session 已过期，询问是否重新登录
3. 用户同意后，运行 `python icloud_tool.py login`，如需 2FA 则让用户发验证码，再运行 `python icloud_tool.py verify <验证码>`

---

## 📋 功能参考

### 🍎 Apple iCloud

#### 照片

```bash
python icloud_tool.py photos albums
python icloud_tool.py photos list 20
python icloud_tool.py photos download 1
```

#### iCloud Drive

```bash
python icloud_tool.py drive list                      # 列出根目录
python icloud_tool.py drive list Work/Projects        # 列出多级目录
python icloud_tool.py drive cd Downloads              # 进入并列出文件夹
python icloud_tool.py drive download Work/doc.pdf     # 下载文件到当前目录
python icloud_tool.py drive download Work/doc.pdf ~/Desktop/doc.pdf  # 下载到指定路径
python icloud_tool.py drive cat Work/notes.txt        # 查看文本文件内容
python icloud_tool.py drive upload local.pdf Work     # 上传文件到指定文件夹
```

#### 查找设备

```bash
python icloud_tool.py devices
```

#### 日历 (CalDAV)

```bash
python icloud_calendar.py list
python icloud_calendar.py today
python icloud_calendar.py week 7
python icloud_calendar.py new 2026-03-15 10:00 11:00 "开会"
python icloud_calendar.py new today "买牛奶" -c "家庭看板"
python icloud_calendar.py search 开会
python icloud_calendar.py delete 开会
```

选项: `--calendar/-c` 指定日历, `--location/-l` 地点, `--description/-d` 描述

#### Session 管理

```bash
# 登录（通过环境变量，非交互式）
export ICLOUD_USERNAME="邮箱"
export ICLOUD_PASSWORD="主密码"
python icloud_tool.py login          # 尝试登录（如需2FA退出码为2）
python icloud_tool.py verify 123456  # 用2FA验证码完成登录

# Session 状态管理
python icloud_auth.py status     # 检查 session
python icloud_auth.py refresh    # 刷新
python icloud_auth.py logout     # 清除
```

---

### 🏥 Apple Health

#### 导入快捷指令

用 iPhone 打开 iCloud 链接添加快捷指令：
https://www.icloud.com/shortcuts/4a5dff0072a6463a9a1fef47d6ec13e2

快捷指令每天自动采集 4 项健康数据（步数、活动能量、心率详细、睡眠详细），
保存为 TXT/JSON 到 iCloud Drive/Shortcuts/Health/。

#### 分析命令

```bash
python health_tool.py today                                  # 分析今日数据
python health_tool.py analyze  health_2026-03-10.txt         # 分析单日文件
python health_tool.py analyze  <dir> [--days 7]              # 分析目录中所有数据
python health_tool.py report   <dir> [--days 7]              # 多日趋势报告
```

默认数据目录: `~/Library/Mobile Documents/com~apple~CloudDocs/Shortcuts/Health/`

#### 数据文件格式

每日文件名: `health_YYYY-MM-DD.txt`（或 `.json`），内容为 JSON：

```json
{
  "date": "2026-03-10",
  "steps": 5444,
  "active_energy_kcal": 169.08,
  "heart_rate": [{"t": "08:32", "v": 72}, ...],
  "sleep": [{"start": "23:30", "end": "00:15", "type": "Core"}, ...]
}
```

#### 分析深度

- **运动与代谢**: 步数评估、每步能耗效率、活动强度判断
- **心率**:
  - 静息心率 / 夜间精确静息心率
  - HRV (RMSSD) 自主神经系统评估
  - 心率突变事件检测（精确到时间点）
  - 昼夜心率差异分析
  - 按时段分布（夜间/上午/下午/晚间）
- **睡眠**:
  - 睡眠周期完整性（Deep→REM 循环计数）
  - Deep/REM/Core 前后半夜分布对比
  - 碎片化指数、睡眠效率
  - 最长连续睡眠段、夜间醒来次数
  - 入睡时间与褪黑素窗口评估
- **交叉关联**:
  - 低运动量 ↔ 低深度睡眠恶性循环检测
  - 高运动量 + 睡眠不足 = 恢复失衡警告
  - 心率偏高 + 低睡眠效率 = 慢性压力信号
  - 晚睡 + 低活动量的昼夜节律紊乱
- **综合评定**: 0-100 分健康评分 + 等级判定

---

## 🔐 凭证汇总

| 服务 | 凭证 | 环境变量 | 获取方式 |
|------|------|---------|---------|
| iCloud 日历 | 应用专用密码 | `ICLOUD_APP_PASSWORD` | appleid.apple.com →「应用专用密码」生成 |
| iCloud 照片/Drive/设备/Health | Apple ID 邮箱 + 主密码 | `ICLOUD_USERNAME` + `ICLOUD_PASSWORD` | 用户直接提供给 AI，AI 通过环境变量自动登录 |
| Apple Health | (不需要) | (不需要) | iPhone 打开 [iCloud 链接](https://www.icloud.com/shortcuts/4a5dff0072a6463a9a1fef47d6ec13e2) 导入快捷指令 |

---

## ⚠️ 注意事项

1. **iCloud 中国大陆**：默认已启用 `ICLOUD_CHINA=1`
2. **iCloud Session**：缓存在 `~/.pyicloud/`，过期时询问用户是否重新登录
3. **Apple Health 零凭证**：无需密码/token，通过 iCloud 链接导入快捷指令
4. **Apple Health 权限**：首次运行快捷指令需手动逐项授权（步数、心率、睡眠、活动能量）
5. **Apple Health 共享数据**：设置→快捷指令→高级→允许共享大量数据
6. **Health 报告时间**：必须晚于快捷指令的数据采集时间，否则数据不完整

---

## 📋 文件结构

```
scripts/
├── icloud_auth.py       # iCloud 认证管理
├── icloud_tool.py       # iCloud 照片 / Drive / 设备
├── icloud_calendar.py   # iCloud 日历 (CalDAV)
└── health_tool.py       # Apple Health 深度分析
```
