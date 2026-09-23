# Agent 用个 omi-cli

> 拨 LLM 驱动个 harness（Claude Code、Cursor、侬自家做个 bot）用个实战指南。

## 为啥迭个 CLI 对 agent 友好

* **JSON 契约稳定。** 加 `--json` 之后 stdout 会输出一只合法 JSON 文档，
  *只有* JSON 文档 — 呒没进度消息，也呒没 spinner。错误会以
  `{"error": "...", "detail": "..."}` 个形式到 stderr。
* **退出码稳定。** `0` 成功 / `1` 用法错误 / `2` 认证错误 /
  `3` 服务器错误 / `4` 限流 / `5` 呒没寻着。Agent 勿需要解析自然语言个
  错误消息，直接按迭个值分支就可以。
* **headless 环境里向勿会弹出交互提示。** 破坏性个命令加 `--yes`（或者 `-y`）；
  传 `--api-key` 或者设 `OMI_API_KEY` 就可以跳过交互登录。
* **重试比较宽容。** `429` 搭 `5xx` 会辣暴露出来之前先带 backoff 重试。

## 认证（人做一趟就够）

用户辣 Omi 网页应用（`https://app.omi.me` → Developer → API Keys）拿
开发者 API key，然后做下底两样里向个一样：

```bash
omi auth login                          # 交互式贴入；key 勿会进 shell 历史
# 或者
export OMI_API_KEY=omi_dev_...          # 临时个，适合容器
```

## Agent 最常做个五桩事体

### 1. 读 memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 建 memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 读 conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 读呒没完成个 action items

```bash
omi action-item list --json --open
```

### 5. 拿 action item 标成完成

```bash
omi action-item complete --json a1b2c3d4
```

## 本地 Desktop API

假使 Omi Desktop 暴露伊个本地 API，agent 勿用云端个开发者 API，
就可以查询设备浪个屏幕历史、摘要、SQL 搭任务：

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# 或者，临时会话用：
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

只有用户明明白白要求辰光，再完成或者删除任务：

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` 会拿截图写到磁盘，
同时照样向 stdout 打印 JSON 拨脚本用。Screenshot ID 一般是从
`local search-screen` 或者对 `screenshots` 表个 SQL 来个。假使 Desktop
返回 `screenshot_pending`、`screenshot_file_missing`、
`screenshot_chunk_corrupted` 迭能结构化失败，JSON 模式会拿 `reason`、
`hint`、`screenshot_id` 迭几个字段保留辣 stderr，agent 就可以拿老个 ID
重试，或者报告准确个阻塞原因。成功个输出辣传给视觉工具之前，
请先用 `file PATH` 验证一遍。

## 实例：Python agent 循环

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """用 JSON 模式调 omi CLI，退出码勿是 0 就抛异常。"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # JSON 模式里向 CLI 会辣 stderr 输出结构化错误：
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# 读全部呒没完成个 action items，拿超过 30 天个侪标成完成。
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 限流哪能处理

Memories：120 趟/钟头。Conversations：25 趟/钟头。批量建：15 趟/钟头。

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # 限流
    err = json.loads(result.stderr)
    # err["detail"] 是迭能样子："Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 小贴士

* 假使侬个 agent 要管多个 Omi 账号，用 `--profile <name>`。
  每隻 profile 有自家个 credential 搭 API base。
* 试本地后端个辰光用 `--api-base http://localhost:8080`。
* 用 `OMI_LOCAL_API_URL` 搭 `OMI_LOCAL_TOKEN`，可以只对一趟运行覆盖
  profile 里向个 Desktop API 设置。
* 调试用 `--verbose` — 伊会拿 `METHOD path → status (Ns)` 记到 stderr，
  勿影响 stdout，所以 JSON 模式照样有效。
* 要拿内容 pipe 进 conversation，用 `--text -`：
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
