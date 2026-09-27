># omi-cli for Agents

> How agents take use omi-cli — practical guide for LLM-driven harnesses (Claude Code, Cursor, and di bots wey you take build).

## Why di CLI good for agents

* **Stable JSON contract.** `--json` dey bring out valid JSON document for stdout and *only* JSON document — no progress messages, no spinners. Errors dey go stderr as `{"error": "...", "detail": "..."}`.
* **Stable exit codes.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate limited / `5` not found. Agents fit branch on top dem without to dey parse errors wey pesin take write.
* **No interactive prompts for headless contexts.** Pass `--yes` (or `-y`) give destructive commands; pass `--api-key` or set `OMI_API_KEY` to take skip interactive login.
* **Forgiving retry behavior.** Dem take retry `429` and `5xx` wit backoff before e go show face.

## Auth (one time, na human being go do am)

Di user go collect dev API key from di Omi web app (`https://app.omi.me` → Developer → API Keys) come either:
```bash
omi auth login                          # interactive paste; di key no dey inside shell history
# abi
export OMI_API_KEY=omi_dev_...          # e no dey tey, e good for containers
```

## Di five tins wey agents dey do pass

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

When Omi Desktop come expose e local API, agents fit take query on-device screen history, recaps, SQL, and tasks without to take use di cloud dev API:
```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# abi, for sessions wey no dey tey:
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

Na only when di user talk am clear you go take complete or delete tasks:
```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` dey write di screenshot go disk and e still dey print JSON go stdout for scripts. Di screenshot ID normally dey come from `local search-screen` or SQL on top di `screenshots` table. If Desktop return structured failure like `screenshot_pending`, `screenshot_file_missing`, or `screenshot_chunk_corrupted`, JSON mode dey keep di `reason`, `hint`, and `screenshot_id` fields for stderr so agents fit take retry wit older ID or report di exact blocker. Validate di outputs wey succeed wit `file PATH` before you pass dem give vision tools.
```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Take call di omi CLI for JSON mode, e go raise if exit code no be success."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Di CLI dey print structured errors go stderr for JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all di open action items come mark anyone wey pass 30 days as complete.
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
if result.returncode == 4:                             # dem don rate-limit am
    err = json.loads(result.stderr)
    # err["detail"] dey be like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Take `--profile <name>` if your agent dey juggle plenty Omi accounts. Each profile get e own credential and API base.
* Take `--api-base http://localhost:8080` for local backend testing.
* Take `OMI_LOCAL_API_URL` and `OMI_LOCAL_TOKEN` to take override di Desktop API settings of di profile for one run.
* Take `--verbose` for debugging — e dey log `METHOD path → status (Ns)` go stderr without to touch stdout, so JSON mode go still dey valid.
* For take pipe content take enta conversation, take `--text -`:
```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
