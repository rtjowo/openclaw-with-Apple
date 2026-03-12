---
name: OpenClaw with Apple
description: Apple iCloud 全功能访问 + Apple Health 深度健康分析 + 双向待办同步
icon: 🍎
os: linux, macos
tools: pyicloud, caldav
install: |
  pip install pyicloud caldav icalendar
tags: icloud, health, tasks, reminders, notes
---

# OpenClaw with Apple

Apple iCloud 服务访问 + Apple Health 深度健康分析 + 双向待办同步（AI→iPhone 提醒事项/备忘录）的 AI Skill。

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

🔓 第 2 步：手动开通健康数据权限

⚠️ 首次运行快捷指令会提示"没有权限"并跳转到「健康」App，但不会自动弹出授权弹窗！
这是 iOS 的已知行为。请按以下步骤手动授权：

1. 打开「快捷指令」App → 找到「Health Daily Export」
2. 点击右上角「...」进入编辑模式
3. 找到每个「查找所有健康样本」操作，点击展开
4. 系统会为每个数据类型（步数、心率、睡眠分析、活动能量、步行+跑步距离）依次弹出授权弹窗，全部点「允许」
5. 授权完成后，点左上角「完成」退出编辑

💡 如果编辑时也没弹窗，还有一个方法：
   iPhone →「设置」→「隐私与安全性」→「健康」→「快捷指令」→ 手动开启所有数据类型

🔐 第 3 步：开启共享大量数据

iPhone →「设置」→「快捷指令」→「高级」→ 开启「允许共享大量数据」
（不开此选项，自动化运行时可能无法导出数据）

▶️ 第 4 步：验证运行

授权完成后，手动运行一次「Health Daily Export」，确认：
  ✅ 没有报权限错误
  ✅ 提示保存文件到 iCloud Drive
  ✅ 文件保存在 iCloud Drive/Shortcuts/Health/ 目录下

⏰ 第 5 步：设置每日自动化

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

### 第四步：询问是否启用待办同步（Tasks）

Health 配置完成后（或不需要 Health 时），继续询问：

```
你需要启用「待办同步」功能吗？
你平时跟我说的待办事项（"明天 2 点开会"、"后天买牛奶"），
我会实时整理成清单，每晚 10 点自动推送到你的 iPhone，
变成「提醒事项」或「备忘录」。
```

#### 用户需要 Tasks：

```
📋 配置待办同步：

🖥️ 第 1 步：安装定时任务（电脑端）

python scripts/setup_tasks_cron.py install

这会在每晚 22:00 自动把待办上传到 iCloud Drive。

📱 第 2 步：在 iPhone 上导入快捷指令

用 iPhone Safari 打开以下链接：

  Tasks Import（提醒事项）:
  https://www.icloud.com/shortcuts/9054c0236adb4909b3dbf72fa58b4933

  Notes Import（备忘录）:
  https://www.icloud.com/shortcuts/56d84868591f4233b7d362c83fb71d59

导入后请各运行一次（首次运行会创建 iCloud Drive 文件夹）。

如果链接无法导入，运行以下命令查看手动创建步骤：
python scripts/generate_tasks_shortcut.py

⏰ 第 3 步：设置 iPhone 自动化

快捷指令 App →「自动化」→ + →「特定时间」：
→ 22:05 运行「Tasks Import」→ 关闭「运行前询问」
→ 22:06 运行「Notes Import」→ 关闭「运行前询问」

✅ 配置完成后，你可以随时告诉我：
  "明天下午两点开会"
  "帮我记一下：后天要交报告"
  "把学习笔记加到备忘录里"
我会实时维护待办清单，每晚自动推送到你的 iPhone。
提醒事项 → iPhone 提醒事项 App
备忘录 → iPhone 备忘录 App（每天合并为一条，标题为日期）
```

#### 用户不需要 Tasks：

**（流程结束）**

---

## 💡 AI 日常行为规则

### ⚠️ 最高优先级：必须实际执行命令

> **你必须实际运行脚本命令来写入数据，不能只是口头回复"搞定了"！**
> 
> 识别到用户说了待办/备忘相关的话后，你必须：
> 1. 在回复中调用 `tasks_tool.py add` 或 `icloud_calendar.py new` 等命令**实际执行**
> 2. 确认命令执行成功后，再告知用户
> 3. **绝对禁止**：不运行任何命令，只在文字回复中说"已添加"或列出日程表。这等于欺骗用户！

### Tasks 相关

1. **主动识别（最重要）**：用户说的话只要涉及以下任何一种，**必须立即自动存储**，无需用户明确说"帮我记"：
   - 提醒类：开会、约会、取快递、交报告、还书、打电话、买东西、预约、面试、截止日期等
   - 备忘类：笔记、想法、灵感、总结、读书笔记、会议纪要、学到的东西、要查的资料等
   - 判断标准：**如果这句话明天可能有用或需要被记住，就存**
   - **不存的情况**：纯闲聊、问答、技术讨论、写代码、改 bug 等不涉及行动或记忆的对话

2. **三种存储目标的判断规则（核心，严格执行）**：

   用户说了一句话后，按以下决策树判断写入哪里，**并实际运行对应命令**：

   ```
   用户说的内容是什么类型？
   │
   ├─ 行动/事件类（开会、洗车、吃饭、取快递...）
   │   │
   │   ├─ 有具体时间点（"2点"、"14:00"、"早上8点"）
   │   │   → ✅ 实际运行: python tasks_tool.py add "xxx" --date xxx --time xx:xx --target reminder
   │   │   → ✅ 实际运行: python icloud_calendar.py new xxx xx:xx xx:xx "xxx"
   │   │
   │   └─ 没有具体时间点（"明天"、"晚上"、"下周"等模糊时间）
   │       → ❌ 不写日历（严禁编造时间！）
   │       → ✅ 实际运行: python tasks_tool.py add "xxx" --date xxx --target reminder
   │
   └─ 知识/笔记/记录类（"记一下xxx"、想法、灵感、纪要、学到的东西...）
       → ❌ 不写日历
       → ❌ 不写提醒事项
       → ✅ 实际运行: python tasks_tool.py add "xxx" --target note --notes "内容"
   ```

   ⛔ **严禁行为**：
   - 用户没说几点，AI 自己脑补一个时间写进日历（如把"明天去洗车"变成"14:00 洗车"）
   - 不执行任何命令，只在回复文字中说"已添加"或列日程表（这是欺骗用户！）

   ✅ **完整示例（含实际要执行的命令）**：

   | 用户说的话 | 必须执行的命令 |
   |-----------|--------------|
   | "明天2点开会" | `python tasks_tool.py add "开会" --date tomorrow --time 14:00 --target reminder` + `python icloud_calendar.py new tomorrow 14:00 15:00 "开会"` |
   | "明天去洗车" | `python tasks_tool.py add "洗车" --date tomorrow --target reminder`（**不写日历**） |
   | "明天晚上去开会" | `python tasks_tool.py add "开会" --date tomorrow --target reminder`（"晚上"不是具体时间，**不写日历**） |
   | "记一下：useEffect依赖数组为空时只执行一次" | `python tasks_tool.py add "useEffect笔记" --target note --notes "依赖数组为空时只执行一次"` |

3. **智能解析**：从自然语言中提取日期（"明天"、"下周三"）、时间（"下午2点"）、优先级（"重要"→high）
4. **主动确认**：命令执行成功后，简短确认告知用户：
   - 写了提醒事项："已加到待办文件中，今晚十点自动同步至提醒事项 ✓"
   - 写了提醒事项+日历："已加到待办文件和日历中，待办今晚十点同步至提醒事项 ✓📅"
   - 写了备忘录："已加到备忘录文件中，今晚十点自动同步至备忘录 ✓"
   - **必须如实告知**，不能说加了日历但实际没加，也不能没说几点就偷偷加日历
5. **合并整理**：用户说"帮我看看明天的待办"时，调用 `tasks_tool.py list --date tomorrow`
6. **手动同步**：用户说"现在就推送到手机"时，调用 `tasks_tool.py sync`（不等定时任务）

### Health 相关

1. **定时报告**：在用户设定的报告时间，自动读取 iCloud Drive 中最新的健康数据文件并生成深度分析
2. **文件路径**：`~/Library/Mobile Documents/com~apple~CloudDocs/Shortcuts/Health/health_YYYY-MM-DD.txt`
3. **分析命令**：`python scripts/health_tool.py analyze <file>` 或 `python scripts/health_tool.py today`
4. **用户主动询问**：随时可以问健康相关问题，AI 自动读取对应日期的数据分析
5. **多日趋势**：`python scripts/health_tool.py report <dir> --days 7`

### iCloud 相关

1. 用户提到日历、照片、文件、设备时，直接调用对应工具执行
2. **任何 iCloud 操作报错时，必须先运行 `python scripts/icloud_auth.py status` 检查 session 状态**
3. 如果 session 过期或不存在，**立即告知用户需要重新登录**，并给出具体步骤：
   ```
   iCloud 登录已过期，需要重新登录：
   请提供你的 Apple ID 邮箱和密码，我来帮你登录。
   ```
4. 用户提供凭证后，运行 `python icloud_tool.py login`，如需 2FA 则让用户发验证码，再运行 `python icloud_tool.py verify <验证码>`
5. **Find My 只能定位 Apple 设备**（iPhone/iPad/Mac/AirTag），无法定位安卓/华为等非 Apple 设备
6. **照片显示异常**：如果 `photos list` 返回的是很久以前的照片（不是最近的），说明 session 或 pyicloud 版本有问题。解决方案：
   - 确认环境变量 `ICLOUD_CHINA=1` 已设置（中国大陆用户必须）
   - 重新登录：`python icloud_tool.py login` + `verify`
   - 检查 pyicloud 版本：`pip install --upgrade pyicloud`

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
python icloud_tool.py drive download Work/doc.pdf     # 下载文件
python icloud_tool.py drive download Work/doc.pdf ~/Desktop/doc.pdf  # 下载到指定路径
python icloud_tool.py drive cat Work/notes.txt        # 查看文本文件内容
python icloud_tool.py drive upload local.pdf Work     # 上传文件
python icloud_tool.py drive mkdir Work/新项目          # 创建文件夹
python icloud_tool.py drive rename Work/旧名 新名      # 重命名
python icloud_tool.py drive delete Work/废弃文件.txt    # 删除文件/文件夹
```

#### 设备列表

```bash
python icloud_tool.py devices                         # 列出所有设备（型号、电量、状态）
```

#### 查找设备 (Find My)

```bash
python icloud_tool.py find locate                     # 定位默认设备(iPhone)
python icloud_tool.py find locate iPad                # 定位指定设备
python icloud_tool.py find status                     # 设备详细状态（电量、充电、位置）
python icloud_tool.py find play                       # 播放声音（找手机）
python icloud_tool.py find lost 13800138000 "请归还"   # 启用丢失模式
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

### 📋 待办同步 (Tasks)

#### 管理待办

```bash
python tasks_tool.py add "开会" --date tomorrow --time 14:00 --priority high
python tasks_tool.py add "读书笔记" --target note --notes "第三章要点"
python tasks_tool.py add "买牛奶" --date 明天 --priority low
python tasks_tool.py list                          # 列出所有
python tasks_tool.py list --date tomorrow          # 列出明天
python tasks_tool.py list --status pending         # 列出未完成
python tasks_tool.py done <id>                     # 标记完成
python tasks_tool.py remove <id>                   # 删除
python tasks_tool.py edit <id> --title "新标题" --time 15:00
python tasks_tool.py clear --done                  # 清理已完成
python tasks_tool.py show                          # 显示完整 JSON
```

选项: `--date` 日期, `--time` 时间, `--priority` high/medium/low, `--notes` 备注, `--target` reminder/note, `--list` 列表名

#### 同步

```bash
python tasks_tool.py sync                          # 上传到 iCloud Drive
python tasks_tool.py sync --download               # 从 iCloud 下载合并
```

#### 定时任务

```bash
python setup_tasks_cron.py install                 # 安装每晚 22:00 自动同步
python setup_tasks_cron.py uninstall               # 卸载
python setup_tasks_cron.py status                  # 查看状态
```

#### 数据流

```
用户对话 → tasks_tool.py add → ~/.openclaw/tasks.json (本地)
                                        │
                                  22:00 launchd 定时
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                    Shortcuts/Tasks/        Shortcuts/Notes/
                    tasks_latest.json       notes_latest.json
                              │                   │
                        22:05 自动化         22:06 自动化
                              ▼                   ▼
                        iPhone 提醒事项     iPhone 备忘录
                        (逐条创建)          (每天一条，标题为日期)
                        (导入后删除文件)     (导入后删除文件)
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
| 待办同步 | 复用 iCloud 凭证 | (同上) | 本地 `~/.openclaw/tasks.json` + iCloud Drive 同步 |

---

## ⚠️ 注意事项

1. **iCloud 中国大陆**：默认已启用 `ICLOUD_CHINA=1`
2. **iCloud Session**：缓存在 `~/.pyicloud/`，过期时询问用户是否重新登录
3. **Apple Health 零凭证**：无需密码/token，通过 iCloud 链接导入快捷指令
4. **Apple Health 权限**：首次运行快捷指令需手动逐项授权（步数、心率、睡眠、活动能量）
5. **Apple Health 共享数据**：设置→快捷指令→高级→允许共享大量数据
6. **Health 报告时间**：必须晚于快捷指令的数据采集时间，否则数据不完整
7. **待办同步**：本地数据在 `~/.openclaw/tasks.json`，每晚 22:00 通过 launchd 自动上传
8. **Tasks/Notes iPhone 端**：Tasks Import 22:05 执行，Notes Import 22:06 执行，各自读取对应文件夹中的 JSON 后删除文件

---

## 📋 文件结构

```
scripts/
├── icloud_auth.py              # iCloud 认证管理
├── icloud_tool.py              # iCloud 照片 / Drive / 设备
├── icloud_calendar.py          # iCloud 日历 (CalDAV)
├── health_tool.py              # Apple Health 深度分析
├── tasks_tool.py               # 待办事项管理（增删改查 + iCloud 同步）
├── setup_tasks_cron.py         # 定时任务安装/卸载
└── generate_tasks_shortcut.py  # iPhone 快捷指令创建指南

~/.openclaw/
├── tasks.json                  # 本地待办数据
└── logs/
    └── tasks-sync.log          # 同步日志
```
