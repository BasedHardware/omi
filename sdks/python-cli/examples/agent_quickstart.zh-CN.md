# 面向 Agent 的 omi-cli

> 面向 LLM 驱动工作流（Claude Code、Cursor、你自己的机器人）的实用指南。

## 为什么这个 CLI 对 Agent 友好

* **稳定的 JSON 契约。** `--json` 只向 stdout 输出一份合法的 JSON 文档 ——
  没有进度提示，没有加载动画。错误以
  `{"error": "...", "detail": "..."}` 的形式写入 stderr。
* **稳定的退出码。** `0` 成功 / `1` 用法错误 / `2` 认证失败 /
  `3` 服务端错误 / `4` 触发限流 / `5` 未找到。Agent 可以直接据此
  分支处理，无需解析自然语言错误信息。
* **无头环境下不会出现交互式提示。** 对破坏性命令传入 `--yes`（或 `-y`）；
  传入 `--api-key` 或设置 `OMI_API_KEY` 即可跳过交互式登录。
* **宽容的重试行为。** 遇到 `429` 和 `5xx` 时会先退避重试，再把错误抛出。

## 认证（由人类一次性完成）

用户从 Omi 网页应用获取开发者 API Key
（`https://app.omi.me` → Developer → API Keys），然后二选一：

```bash
omi auth login                          # 交互式粘贴；密钥不会进入 shell 历史
# 或
export OMI_API_KEY=omi_dev_...          # 临时生效，适合容器环境
```

## Agent 最常做的五件事

### 1. 读取记忆

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 创建一条记忆

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 读取对话

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 读取未完成的待办事项

```bash
omi action-item list --json --open
```

### 5. 把待办事项标记为完成

```bash
omi action-item complete --json a1b2c3d4
```

## 本地 Desktop API

当 Omi Desktop 暴露其本地 API 时，Agent 可以查询设备端的屏幕历史、回顾、
SQL 和任务，而无需使用云端开发 API：

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 或用于临时会话：
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

只有在用户明确要求时，才完成或删除任务：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 会把截图写入磁盘，
同时仍向 stdout 输出 JSON 供脚本使用。截图 ID 通常来自
`local search-screen`，或来自对 `screenshots` 表执行 SQL 的结果。
如果 Desktop 返回结构化失败（例如 `screenshot_pending`、
`screenshot_file_missing` 或 `screenshot_chunk_corrupted`），JSON 模式
会在 stderr 上保留 `reason`、`hint` 和 `screenshot_id` 字段，
方便 Agent 改用更早的 ID 重试，或准确报告阻塞点。把成功输出交给视觉工具
之前，先用 `file PATH` 验证。

## 完整示例：Python Agent 循环

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """以 JSON 模式调用 omi CLI；退出码非成功时抛错。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # 在 JSON 模式下，CLI 会向 stderr 输出结构化错误：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 读取所有未完成的待办事项，把超过 30 天的标记为完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 处理限流

记忆：120 次/小时。对话：25 次/小时。批量创建：15 次/小时。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 触发限流
    err = json.loads(result.stderr)
    # err["detail"] 形如："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 实用提示

* 如果你的 Agent 需要同时管理多个 Omi 账号，使用 `--profile <name>`。
  每个 profile 拥有各自的凭据和 API base。
* 本地后端联调时使用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 和 `OMI_LOCAL_TOKEN` 可以在单次运行中覆盖
  profile 里的 Desktop API 设置。
* 调试时使用 `--verbose` —— 它把 `METHOD path → status (Ns)` 记录到
  stderr，不影响 stdout，因此 JSON 模式依然合法。
* 需要把内容管道传入对话时，使用 `--text -`：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
