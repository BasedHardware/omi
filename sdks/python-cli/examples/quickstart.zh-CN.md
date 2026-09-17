# omi-cli 简体中文快速入门

> 从终端与 Omi 对话。专为人类和 AI Agent 设计。

`omi-cli` 是 [Omi](https://omi.me) 开发者 API 的命令行接口。
它提供面向 Agent 的命令，覆盖 Omi 维护的四个核心资源：

* **memories** — 系统保存的事实和记忆
* **conversations** — 已捕获并处理的对话
* **action items** — 待办事项和跟进任务
* **goals** — 跟踪的进度指标

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **文档:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **源码:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安装

推荐使用 `pipx` 进行隔离安装，避免与其他 Python 包冲突。

```bash
# 推荐方式：使用 pipx 安装
pipx install omi-cli

# 或使用 pip 安装
pip install omi-cli
```

> **注意：PyPI 包名是 `omi-cli`，不是 `omi`。**
> * PyPI 上的分发包名为 **`omi-cli`**（裸名 `omi` 属于另一个无关项目）。
> * 安装后命令行工具名为 **`omi`**。

安装完成后，验证：

```bash
omi --version
omi --help
```

---

## 2. 登录认证

`omi-cli` 支持两种认证方式。

| 认证方式 | 适用场景 | 命令 |
| :--- | :--- | :--- |
| **开发者 API Key** (`omi_dev_*`) | CI/CD、自动化、Agent | `omi auth login --api-key ...` 或直接设置环境变量 |
| **浏览器登录** (Google/Apple) | 个人日常使用 | `omi auth login --browser` |

### 交互式登录（推荐）

如果你不确定选择哪种方式，运行交互式登录，按提示选择：

```bash
omi auth login
# 1) Browser → 使用 Google 或 Apple 登录（推荐人类用户）
# 2) API key → 粘贴来自 app.omi.me 的开发者密钥（推荐 Agent/CI）
```

选择浏览器登录后，会打开浏览器完成 OAuth 流程。

### 浏览器登录

```bash
omi auth login --browser
```

### API Key 登录

从 [app.omi.me](https://app.omi.me) 获取密钥，进入 **Developer → API Keys** 页面。

```bash
# 交互式输入密钥（安全，不会回显）
omi auth login --api-key omi_dev_...

# 或通过环境变量设置（适合 CI/CD 和自动化）
export OMI_API_KEY=omi_dev_...
```

设置 `OMI_API_KEY` 环境变量后，无需再次执行 `auth login`，
CLI 会自动使用该密钥，无需交互式登录。适合在 CI/CD 或自动化脚本中使用。

### 检查认证状态

有两个相关命令，请注意区分：

* `omi auth status` — 检查**本地**认证状态：是否有密钥、是否过期等。
  不会向服务端发送请求。
* `omi auth whoami` — 向 Omi 服务端验证**实际身份**：返回当前密钥对应的账户信息。
  需要网络连接。

```bash
omi auth status    # 本地认证状态，快速检查
omi auth whoami    # 向服务端验证身份
```

如果遇到密钥过期或权限问题，刷新认证：

```bash
omi auth refresh
```

退出登录：

```bash
omi auth logout
```

---

## 3. 读取你的数据

以下命令只读取对应资源，不会修改任何数据：

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

| 命令组 | 对应内容 |
| --- | --- |
| `memory` | 系统保存的事实和记忆 |
| `conversation` | 已捕获并处理的对话 |
| `action-item` | 待办事项 |
| `goal` | 目标及进度 |

列表通常只返回一页。需要后续页时，先运行相应的 `list --help` 查看该命令支持的分页选项。

> 空结果不一定表示登录失败；以命令的错误信息和退出状态为准。

---

## 4. 在脚本中使用 JSON 输出

`--json` 是全局选项，放在命令组之前：

```bash
omi --json memory list --limit 5
omi --json conversation list --limit 5
```

输出为标准 JSON，可直接传递给 `jq` 或其他工具处理：

```bash
omi --json memory list | jq '.[] | {id, content}'
```

### 在 Shell 脚本中使用

```bash
# 获取最近 5 条记忆的 ID
ids=$(omi --json memory list --limit 5 | jq -r '.[].id')

# 遍历并处理每条记忆
for id in $ids; do
  echo "Processing memory: $id"
  # 在此添加你的处理逻辑
done
```

### 在 Python 中使用

```python
import subprocess, json

result = subprocess.run(
    ["omi", "--json", "memory", "list", "--limit", "5"],
    capture_output=True, text=True
)
memories = json.loads(result.stdout)
for m in memories:
    print(m["id"], m.get("content", "")[:80])
```

---

## 5. 常见退出码

| 退出码 | 含义 | 建议 |
| --- | --- | --- |
| `0` | 成功 | — |
| `1` | 通用错误 | 检查错误信息 |
| `2` | 认证失败 | 运行 `omi auth login` |
| `3` | 网络错误 | 检查网络连接 |

---

## 更多信息

* 完整命令参考：`omi --help` 或 `omi <command> --help`
* 官方文档：[docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* 问题反馈：[GitHub Issues](https://github.com/BasedHardware/omi/issues)

---

*本快速入门由 AUTO (AI Agent) 创建。对应 bounty: Issue #13058*
