# omi-cli for agents

> Practical guide for LLM-driven harnesses (Claude Code, Cursor, your own bots).

## Why the CLI is agent-friendly

* **Stable JSON contract.** `--json` emits a valid JSON document to stdout and
  *only* a JSON document — no progress messages, no spinners. Errors go to
  stderr as `{"error": "...", "detail": "..."}`.
* **Stable exit codes.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate
  limited / `5` not found. Agents can branch on these without parsing
  natural-language errors.
* **No interactive prompts in headless contexts.** Pass `--yes` (or `-y`) to
  destructive commands; pass `--api-key` or set `OMI_API_KEY` to skip
  interactive login.
* **Forgiving retry behavior.** `429` and `5xx` are retried with backoff
  before surfacing.

## Auth (one-time, by the human)

The user gets a dev API key from the Omi web app
(`https://app.omi.me` → Developer → API Keys) and either:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## The five things agents do most

### 1. Read memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Create a memory

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

### 5. Mark an action item done

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

When Omi Desktop exposes its local API, agents can query on-device screen
history, recaps, SQL, and tasks without using the cloud dev API:

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

Only complete or delete tasks when the user clearly asks:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` writes the screenshot to
disk and still prints JSON to stdout for scripts.

## Worked example: Python agent loop

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

## Handling rate limits

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Use `--profile <name>` if your agent juggles multiple Omi accounts. Each
  profile has its own credential and API base.
* Use `--api-base http://localhost:8080` for local backend testing.
* Use `OMI_LOCAL_API_URL` and `OMI_LOCAL_TOKEN` to override profile-local
  Desktop API settings for one run.
* Use `--verbose` for debugging — it logs `METHOD path → status (Ns)` to stderr
  without affecting stdout, so JSON mode stays valid.
* For piping content into a conversation, use `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
