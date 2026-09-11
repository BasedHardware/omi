# omi-cli 简体中文快速入门指南

> 在终端中与 Omi 交互的实用指南。专为人类开发者与 AI Agent 设计。

`omi-cli` 是用于操作 [Omi](https://omi.me) 开发者 API 的官方命令行工具。它以简洁、可脚本化、JSON 优先的方式，让您能够轻松管理 Omi 维护的四大核心资源：记忆（Memories）、对话（Conversations）、行动项（Action Items）和目标（Goals）。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **官方文档:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **源码仓库:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安装

推荐使用 `pipx` 进行隔离安装，避免全局依赖污染：

```bash
# 推荐：使用 pipx 进行隔离安装
pipx install omi-cli

# 或者使用传统 pip 安装
pip install omi-cli
```

> **重要提示：包名与命令名区别**
> * PyPI 上的分发包名为 **`omi-cli`**（单独的 `omi` 包属于其他无关项目）。
> * 安装完成后在终端中执行的命令为 **`omi`**。

验证安装：

```bash
omi --version
omi --help
```

---

## 2. 身份验证 (Authentication)

`omi-cli` 支持两种登录认证方式：

| 认证方式 | 适用场景 | 命令示例 |
| :--- | :--- | :--- |
| **开发者 API Key (`omi_dev_*`)** | CI/CD 自动化、脚本、AI Agent | `omi auth login --api-key ...` 或环境变量 |
| **浏览器 OAuth (Google / Apple)** | 本地开发机上的个人用户 | `omi auth login --browser` |

### 交互式登录
直接运行不带参数的命令，系统会弹出交互菜单：

```bash
omi auth login
# 1) Browser — 弹出浏览器使用 Google 或 Apple 账户登录（适合人类）
# 2) API key — 粘贴来自 app.omi.me 的开发者 Key（适合 Agent/CI）
```

### 浏览器直接登录
```bash
omi auth login --browser
```

### 使用 API Key 登录
在 [app.omi.me](https://app.omi.me) 的「Developer → API Keys」中获取 Key：

```bash
# 使用命令行参数设置
omi auth login --api-key omi_dev_...

# 或使用环境变量（非常适合容器或自动化流水线）
export OMI_API_KEY=omi_dev_...
```

### 检查认证状态
* `omi auth status`：查看本地保存的配置文件、脱敏后的凭据以及过期时间（离线可用）。
* `omi auth whoami`：向 Omi 服务器发起实际验证请求，确认凭据当前有效（需要网络连接）。

```bash
omi auth status
omi auth whoami
```

退出登录并清理本地凭据：
```bash
omi auth logout
```

---

## 3. 基础操作

管理 Omi 的四大核心数据资源：

### 记忆 (Memories)
系统学习并记录的关于用户的事实和知识。

```bash
# 列出记忆列表
omi memory list

# 创建一条新记忆
omi memory create "用户更喜欢深色模式界面" --category lifestyle

# 根据 ID 查看单条记忆详情
omi memory get <ID_MEMORY>
```

### 对话 (Conversations)
硬件设备或应用记录的完整语音/文本对话。

```bash
# 查看最近 5 条对话
omi conversation list --limit 5

# 查看对话详情及完整转写文本
omi conversation get <ID_CONVERSATION> --include-transcript
```

### 行动项 (Action Items)
从对话中自动提取出的待办事项和跟进任务。

```bash
# 仅列出未完成的待办事项
omi action-item list --open

# 将某项任务标记为已完成
omi action-item complete <ID_ACTION>
```

### 目标 (Goals)
正在追踪进度的各项量化目标。

```bash
# 列出当前所有目标
omi goal list
```

---

## 4. 脚本与 JSON 输出 (`--json`)

`omi-cli` 原生支持 JSON 输出格式。配合 `jq` 或 Python 处理数据时，请将 `--json` 作为**全局选项放在子命令之前**：

```bash
# 输出记忆列表的 JSON 并提取 ID 与内容
omi --json memory list | jq '.[] | {id, content, category}'

# 获取最近对话的标题列表
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 输出所有未完成待办事项的 JSON
omi --json action-item list --open | jq '.'
```

> **注意：** `--json` 必须放在子命令（如 `memory`, `conversation`）**之前**：
> * 正确: `omi --json memory list`
> * 错误: `omi memory list --json`

---

## 5. 退出代码 (Exit Codes)

为了便于在脚本和自动化流程中做条件判断，`omi-cli` 定义了标准化的退出码：

| 退出码 | 含义 | 说明 |
| :---: | :--- | :--- |
| `0` | 成功 (Success) | 命令执行完成且正常返回 |
| `1` | 使用方式错误 (Usage Error) | 参数无效、缺少必填选项等 |
| `2` | 认证错误 (Auth Error) | 未登录、API Key 无效或凭据已过期 |
| `3` | 服务器/网络错误 (Server Error) | 5xx 响应、网络超时或连接失败 |
| `4` | 速率限制 (Rate Limited) | HTTP 429 请求过于频繁 |
| `5` | 资源不存在 (Not Found) | HTTP 404 找不到指定的 ID |

---

## 6. 各终端环境变量配置

### Bash / Zsh (Linux / macOS)
```bash
# 设置 API Key
export OMI_API_KEY="omi_dev_your_actual_key_here"

# 以 JSON 模式执行命令
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# 设置 API Key
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# 在 PowerShell 中解析 JSON 输出
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. 本地 Desktop API 集成

当 Omi Desktop 桌面应用在本地运行时，可以直接查询本地屏幕 OCR 历史与数据库，无需访问云端：

```bash
# 配置本地 API 地址与 Token
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# 查看本地服务连接状态
omi --json local status

# 在屏幕历史记录中搜索关键字
omi --json local search-screen "发票" --days 7 --app Safari
```

---

## 8. 多配置文件管理 (Profiles)

如果您需要在不同账户（如个人账号和工作账号）之间切换，可以使用 `--profile` 选项。配置会保存在 `~/.omi/config.toml` 中：

```bash
# 登录并保存到 personal 配置文件
omi --profile personal auth login

# 登录并保存到 work 配置文件
omi --profile work auth login

# 在特定配置文件下执行操作
omi --profile work memory list
```
