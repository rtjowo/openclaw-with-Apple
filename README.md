# 🍎 OpenClaw with Apple

Apple iCloud 全功能访问 + Apple Health 深度健康分析 + 双向待办/备忘录同步的 AI Skill。

## 功能

| 服务 | 能力 |
|------|------|
| 🍎 iCloud | 照片、iCloud Drive、查找设备、日历 (CalDAV) |
| 🏥 Health | 深度健康分析 — 心率 HRV / 睡眠周期 / 压力评估 / 交叉关联诊断 |
| 📋 Tasks | AI 对话 → 提醒事项自动推送到 iPhone |
| 📝 Notes | AI 对话 → 备忘录自动推送到 iPhone |

## 快速开始

```bash
pip install pyicloud caldav icalendar

# Apple iCloud
python scripts/icloud_auth.py login              # 一次性登录（密码不保存）
export ICLOUD_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx" # 日历用
```

## 待办 & 备忘录同步

对话中提到的待办事项和笔记，自动分类推送到 iPhone：

- **提醒事项**（"明天 2 点开会"）→ iPhone 提醒事项 App
- **备忘录**（"帮我记个读书笔记"）→ iPhone 备忘录 App（每天合并为一条）

### 1. 安装 iPhone 快捷指令

在 iPhone Safari 中打开链接，点击「获取快捷指令」：

- **Tasks Import**（提醒事项）: https://www.icloud.com/shortcuts/9054c0236adb4909b3dbf72fa58b4933
- **Notes Import**（备忘录）: https://www.icloud.com/shortcuts/56d84868591f4233b7d362c83fb71d59

> ⚠️ 导入后请各运行一次，首次运行会创建 iCloud Drive 文件夹。

### 2. 安装定时同步

```bash
python scripts/setup_tasks_cron.py install   # 每晚 22:00 自动上传到 iCloud
```

### 3. 设置 iPhone 自动化

快捷指令 App → 自动化 → + → 特定时间：
- 22:05 运行「Tasks Import」
- 22:06 运行「Notes Import」

### 数据流

```
用户对话 → AI 判断类型 → tasks_tool.py add
                              │
                        22:00 自动上传
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
         Shortcuts/Tasks/        Shortcuts/Notes/
         tasks_latest.json       notes_latest.json
                    │                   │
              22:05 自动化         22:06 自动化
                    ▼                   ▼
              iPhone 提醒事项     iPhone 备忘录
                                 (yyyy-MM-dd 备忘录)
```

### 命令参考

```bash
python scripts/tasks_tool.py add "开会" --date tomorrow --time 14:00 --priority high
python scripts/tasks_tool.py add "读书笔记" --target note --notes "第三章要点"
python scripts/tasks_tool.py list
python scripts/tasks_tool.py sync              # 手动上传到 iCloud
```

## Apple Health — 零配置健康分析

无需密码、无需 token，3 步启用：

1. **iPhone 打开链接** → 添加快捷指令：
   https://www.icloud.com/shortcuts/4a5dff0072a6463a9a1fef47d6ec13e2

2. **开通权限** → 手动运行一次，逐项允许（步数、心率、睡眠、活动能量）

3. **设置自动化** → 快捷指令 App → 自动化 → 每天 23:00 运行

> ⚠️ iPhone「设置」→「快捷指令」→「高级」→ 开启「允许共享大量数据」

### 分析示例

```bash
python scripts/health_tool.py today                          # 今日分析
python scripts/health_tool.py analyze health_2026-03-10.txt  # 单日文件
python scripts/health_tool.py report <dir> --days 7          # 7 天趋势
```

### 分析深度

- **心率**：夜间精确静息心率、HRV (RMSSD) 自主神经评估、心率突变事件定位、昼夜差异分析
- **睡眠**：周期完整性、Deep/REM/Core 前后半夜分布、碎片化指数、睡眠效率
- **压力**：基于 HRV + 白天心率 + 睡眠质量的综合压力判断
- **交叉关联**：运动↔睡眠恶性循环检测、心率↔睡眠联动、作息节律评估
- **综合评分**：0-100 分健康评定

## iCloud 使用

```bash
# 照片
python scripts/icloud_tool.py photos albums
python scripts/icloud_tool.py photos list 10
python scripts/icloud_tool.py photos download 1

# iCloud Drive
python scripts/icloud_tool.py drive list

# 设备
python scripts/icloud_tool.py devices

# 日历
python scripts/icloud_calendar.py today
python scripts/icloud_calendar.py new 2026-03-15 10:00 11:00 "开会"
python scripts/icloud_calendar.py search "开会"
```

## 认证

| 凭证 | 用途 | 获取方式 |
|------|------|---------|
| Apple ID 主密码 | 照片/Drive/设备 | `icloud_auth.py login` 交互输入 |
| 应用专用密码 | CalDAV 日历 | [appleid.apple.com](https://appleid.apple.com) 生成 |
| Apple Health | (不需要) | iPhone 打开 iCloud 链接导入快捷指令 |
| 待办/备忘录同步 | 复用 iCloud 凭证 | iPhone 导入快捷指令 |

## 文件结构

```
scripts/
├── icloud_auth.py              # iCloud 认证管理
├── icloud_tool.py              # 照片 / Drive / 设备
├── icloud_calendar.py          # 日历 (CalDAV)
├── health_tool.py              # Health 深度分析
├── tasks_tool.py               # 待办/备忘录管理 + iCloud 同步
├── setup_tasks_cron.py         # 定时任务安装/卸载
└── generate_tasks_shortcut.py  # 快捷指令用户指引
```

## 文档

- [完整 Skill 文档](SKILL.md)

## License

MIT
