# omi-cli — Vahcuengh quickstart

> 在终端操作 Omi 个实用指南。人和 AI 代理都能用。

`omi-cli` 是 [Omi](https://omi.me) 开发者 API 个官方命令行客户端。
佢对 Omi 个四个主要资源 — 记忆、对话、行动项目、目标 — 提供快速、可脚本化个访问。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **文档:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **源代码:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安装

推荐用 `pipx`:佢会把工具安装到独立个环境,
不会同你项目个依赖冲突。

```bash
# 推荐:用 pipx 安装
pipx install omi-cli

# 或者用 pip
pip install omi-cli
```

> **重要:包名同命令名不一样。**
> * 安装个包是 **`omi-cli`** (`omi` 是另外一个无关个项目)。
> * 安装好之后执行个命令是 **`omi`**。

确认一下能不能用:

```bash
omi --version
omi --help
```

---

## 2. 认证

`omi-cli` 支持两种登录方式。

| 方式 | 适合 | 命令 |
| :--- | :--- | :--- |
| **开发者密钥 (`omi_dev_*`)** | CI/CD、脚本、AI 代理 | `omi auth login --api-key ...` 或环境变量 |
| **浏览器登录 (Google/Apple)** | 在自己电脑上工作 | `omi auth login --browser` |

### 交互式登录

不带选项运行,佢会问你想用哪种方式。

```bash
omi auth login
# 1) Browser — 用 Google 或 Apple 登录(给人用)
# 2) API key — 把 app.omi.me 拿来个开发者密钥贴上去(给代理/CI)
```

选密钥个话,输入会藏起来,密钥不会留在终端历史里。

### 直接用浏览器登录

```bash
omi auth login --browser
```

### 用开发者密钥登录

密钥在 [app.omi.me](https://app.omi.me) 个 **Developer → API Keys** 拿。

```bash
# 把密钥存到配置
omi auth login --api-key omi_dev_...

# 或者用环境变量传 — 对 CI/CD 和容器更好
export OMI_API_KEY=omi_dev_...
```

`OMI_API_KEY` 环境变量在激活个配置档没存密钥时才用,
所以在容器里不用写东西到硬盘。如果配置档已经有密钥,
那个密钥优先级比环境变量高。

### 检查访问

两个命令答个是不同个问题,别混淆:

* `omi auth status` — **本地**存个什么:配置档、藏起来个密钥、到期日。
  不用网络。
* `omi auth whoami` — 对 **Omi 服务器** 个请求:确认密钥真的会被接受。
  需要网络。

```bash
omi auth status    # 本地检查,离线可以
omi auth whoami    # 服务器检查
```

把快到期个令牌不用再登录就更新 — 这个命令只适用 **浏览器/OAuth 会话**。
用 API 密钥(`omi_dev_*`)认证个配置档,`omi auth refresh` 会因用法错误(代码 1)
失败 — 没令牌可更新 — 有需要就到 Omi 网页应用换密钥:

```bash
omi auth refresh
```

登出:

```bash
omi auth logout
```

---

## 3. 基本命令

### 记忆 (memories)

系统记住你事实和知识。

```bash
# 记忆列表
omi memory list

# 新增一个
omi memory create "用户喜欢深色主题" --category lifestyle

# 看特定一个
omi memory get <MEMORY_ID>
```

### 对话 (conversations)

设备或应用个语音和文字历史。

```bash
# 最新个 5 个对话
omi conversation list --limit 5

# 带转录个完整对话
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 行动项目 (action items)

Omi 从对话推理出来个任务。

```bash
# 只看没完成个
omi action-item list --open

# 标记完成
omi action-item complete <ACTION_ITEM_ID>
```

### 目标 (goals)

```bash
# 目标列表
omi goal list

# 记录新个进度值(需要两个参数:目标和数值)
omi goal progress <GOAL_ID> 25

# 改变历史
omi goal history <GOAL_ID>
```

---

## 用自然语言问 (`ask`)

另外一个顶层命令:接受自然语言个问题,
答案从你个对话建起来。

```bash
omi ask "搬家个事情我决定什么了"
omi --json ask "这个礼拜我答应要完成什么行动项目"
```

---

## 4. JSON 和脚本 (`--json`)

`omi-cli` 能生成机器可读个 JSON。`--json` 选项是 **全局**,
要放在子命令个 **前面**。

```bash
# 记忆:提出 id、文字、类别
omi --json memory list | jq '.[] | {id, content, category}'

# 最近对话个标题
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 没完成个行动项目
omi --json action-item list --open | jq '.'
```

> **常见个错。** `--json` 在子命令前面,不是后面。
> * 对: `omi --json memory list`
> * 错: `omi memory list --json`

`--json` 模式里,给人看个进度信息和旋转图标没有了 —
stdout 只有一个有效个 JSON 文档。错误去 stderr,
形状是 `{"error": "...", "detail": "..."}`。

---

## 5. 退出代码

脚本用来分支个稳定退出代码。

| 代码 | 意思 |
| :--- | :--- |
| `0` | 成功 |
| `1` | 用法错误(标志错、必需个参数没) |
| `2` | 认证失败 — 需要登录 |
| `3` | 服务器/网络错误 |
| `4` | 速率限制 — 过一下再试 |
| `5` | 资源找不到 |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "那个记忆没在" ;;
    *) echo "错误 $code" ;;
  esac
fi
```

---

## 6. 配置档和配置

如果你有多个账号或环境,用配置档分开。
配置存在 `~/.omi/config.toml`。

```bash
# 登录个人配置档
omi --profile personal auth login

# 登录工作配置档
omi --profile work auth login

# 在特定配置档执行命令
omi --profile work memory list
```

用哪个配置档按这个顺序决定:`--profile` 选项(或 `-p`)
优先全部;再是 `OMI_PROFILE` 环境变量;再是 `~/.omi/config.toml`
个激活配置档;最后 `default` 配置档做后备。

看和改自己个配置:

```bash
# 现在设个是什么
omi config show

# 配置文件在哪
omi config path

# 改数值
omi config set api_base https://api.omi.me
```

---

## 7. 下一步

* [`agent_quickstart.md`](./agent_quickstart.md) — 把 `omi-cli` 接 AI 代理个方式。
* [`shell_examples.sh`](./shell_examples.sh) — 现成个 shell 示例。
* [Omi 文档](https://docs.omi.me/doc/developer/cli/introduction) — 完整个命令参考。
