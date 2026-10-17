# omi-cli 予代理程式

> 予 LLM 驅動 harness 个實用指南 (Claude Code, Cursor, 自家个機器人)。

## 為啥物 CLI 適合代理程式

* **穩定个 JSON 契約** `--json` emits a valid JSON document to stdout and *only* a JSON document — no progress messages, no spinners. Errors go to stderr as `{"error": "...", "detail": "..."}`.
* **穩定个退出碼** `0` ok / `1` usage / `2` auth / `3` server / `4` rate limited / `5` not found.
* **headless 情境無互動提示** Pass `--yes` (or `-y`) to destructive commands; pass `--api-key` or set `OMI_API_KEY` to skip interactive login.
* **容忍个重試行為** `429` and `5xx` are retried with backoff before surfacing.

## 認證 (一擺,由人做)

The user gets a dev API key from the Omi web app
(`https://app.omi.me` → Developer → API Keys) and either:

```bash
omi auth login                          # interactive paste; key not in shell history
# # 抑是
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## 代理程式上捷做个五件事

### 1. 讀 memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. 起一个 memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. 讀 conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. 讀開个 action items

```bash
omi action-item list --json --open
```

### 5. 將 action item 標記完成

```bash
omi action-item complete --json a1b2c3d4
```

## 在地 Desktop API

When Omi Desktop exposes its local API, agents can query on-device screen
history, recaps, SQL, and tasks without using the cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # or, for ephemeral sessions:
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

干焦佇使用者明確要求時完成抑是刪除任務:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` writes the screenshot to
disk and still prints JSON to stdout for scripts. The screenshot ID usually comes
from `local search-screen` or SQL over the `screenshots` table. If Desktop returns
a structured failure such as `screenshot_pending`, `screenshot_file_missing`, or
`screenshot_chunk_corrupted`, JSON mode preserves `reason`, `hint`, and
`screenshot_id` on stderr so agents can retry an older ID or report the exact
blocker. Validate successful outputs with `file PATH` before passing them to
vision tools.

## 實作範例:Python 代理程式迴圈

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## 處理速率限制

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## 提示

* 假使代理程式處理多個 Omi 帳號,用 `--profile <name>`。逐个 profile
  有自家个 credential 佮 API base。
* Use `--api-base http://localhost:8080` for local backend testing.
* Use `OMI_LOCAL_API_URL` and `OMI_LOCAL_TOKEN` to override profile-local
  Desktop API settings for one run.
* Use `--verbose` for debugging — it logs `METHOD path → status (Ns)` to stderr
  without affecting stdout, so JSON mode stays valid.
* For piping content into a conversation, use `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
