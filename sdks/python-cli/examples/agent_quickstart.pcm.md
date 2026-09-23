# How agents go take use omi-cli

> Practical guide for LLM-driven harnesses (Claude Code, Cursor, your own bots).

## Why di CLI dey agent-friendly

* **Stable JSON contract.** `--json` go emit one valid JSON document to stdout and
  *only* JSON document — no progress messages, no spinners. Errors dey go
  stderr as `{"error": "...", "detail": "..."}`.
* **Stable exit codes.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate
  limited / `5` not found. Agents fit branch on top dem without parsing
  natural-language errors.
* **No interactive prompts for headless contexts.** Pass `--yes` (or `-y`) for
  destructive commands; pass `--api-key` or set `OMI_API_KEY` to skip
  interactive login.
* **Forgiving retry behavior.** Dem dey retry `429` and `5xx` wit backoff
  before dem go surface am.

## Auth (one-time, na human go do am)

Di user go get dev API key from di Omi web app
(`https://app.omi.me` → Developer → API Keys) and do one of dis:

```bash
omi auth login                          # paste am interactively; key no dey shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, e good for containers
```

## Di five things wey agents dey do pass

### 1. Read memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Create memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Read conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Read open action items

```bash
omi action-item list --json --open
```

### 5. Mark action item as done

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

When Omi Desktop expose im local API, agents fit query on-device screen
history, recaps, SQL, and tasks without using di cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Only complete or delete tasks when di user clearly ask:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` go write di screenshot to
disk and e go still print JSON to stdout for scripts. Di screenshot ID dey
usually come from `local search-screen` or SQL on top di `screenshots` table.
If Desktop return structured failure like `screenshot_pending`,
`screenshot_file_missing`, or `screenshot_chunk_corrupted`, JSON mode go keep
di `reason`, `hint`, and `screenshot_id` fields for stderr so agents fit retry
older ID or report di exact blocker. Validate successful outputs wit `file
PATH` before you pass dem to vision tools.

## Worked example: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Call di omi CLI for JSON mode, raise error if exit code no be success."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Di CLI dey print structured errors to stderr for JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all di open action items, mark anything wey pass 30 days as complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## How to handle rate limits

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] go look like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Use `--profile <name>` if your agent dey juggle multiple Omi accounts. Each
  profile get im own credential and API base.
* Use `--api-base http://localhost:8080` for local backend testing.
* Use `OMI_LOCAL_API_URL` and `OMI_LOCAL_TOKEN` to override profile-local
  Desktop API settings for one run.
* Use `--verbose` for debugging — e dey log `METHOD path → status (Ns)` to
  stderr without touching stdout, so JSON mode still dey valid.
* To pipe content inside conversation, use `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
