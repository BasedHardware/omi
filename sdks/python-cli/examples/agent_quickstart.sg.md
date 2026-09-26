# omi-cli tî mâ rêmâ-kôzô

> Tî kôzô tî aïssa LLM (Claude Code, Cursor, môkô bot niono).

## Ndía kôzo tî omi-cli ma ndakpa tî mâ rêmâ-kôzô

* **JSON contract.** `--json` kode tî JSON mo stdout *lâla mondu* — tagâ nâ yâ Windows, tagâ na spinner. Nzala kode mo stderr me`{"error": "...", "detail": "..."}`.
* **Exit code.** `0` ma ndakpa / `1` uso / `2` auth / `3` server / `4` rate limited / `5` mâ rêmâ. Mâ rêmâ-kôzô fe ke la JSON contract ma lâla.
* **Interactive prompt te headless.** Kode `--yes` (o `-y`) tî destructive command; kode `--api-key` o `OMI_API_KEY` tî ba login interactive.
* **Mvondo retry.** `429` a `5xx` kode retry ma backoff ndoki.

## Auth (tî ya dô, mo tâ nâ ngâ)

Tâ kô kode API key tî dev mo Omi web app
(`https://app.omi.me` → Developer → API Keys):

```bash
omi auth login                          # paste interactive; key niono shell history
# o
export OMI_API_KEY=omi_dev_...          # ephemeral, container
```

## Nokô kôzo tî mâ rêmâ-kôzô

### 1. Ti bängä memory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kô memory mo ntâ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ti bängä conversation

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ti bängä action item

```bash
omi action-item list --json --open
```

### 5. Marque action item tî ndakpa

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Omi Desktop le wa local API, mâ rêmâ-kôzô kode ti bängä screen history, recap, SQL a task te device, ba na cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, ephemeral session:
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

Kô complete na e delete task ba ye kô ûa se nâ nângâ mâ rêmâ mâralâ tî kô ye:


Only complete or delete tasks when the user clearly asks:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` write screenshot mo file
a kode JSON mo stdout tî script. Screenshot ID bâ `local search-screen`
o SQL table `screenshots`. Desktop wa failure
`screenshot_pending`, `screenshot_file_missing`,
`screenshot_chunk_corrupted`, JSON mode yâ `reason`, `hint`,
`screenshot_id` mo stderr tî mâ rêmâ-kôzô retry ID tî ndângo
o report blocker. Validate success output `file PATH` ndoki
vision tool.

## Example: Python agent loop

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

## Rate limit

Memory: 120/hr. Conversation: 25/hr. Batch create: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Nsanu

* Kode `--profile <name>` tî mâ rêmâ-kôzô account Omi mono. Profile mono
  credential a API base mono.
* Kode `--api-base http://localhost:8080` tî local backend test.
* Kode `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` tî override profile-local
  Desktop API tî run mono.
* Kode `--verbose` tî debug — kode `METHOD path → status (Ns)` mo stderr
  niono stdout, JSON mode ma ndakpa.
* Pipe content mo conversation, kode `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
