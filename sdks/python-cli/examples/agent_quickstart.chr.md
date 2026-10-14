# omi-cli ᏣᎳᎩ ᎤᏍᏗᏍᏓᏅ ᎯᎠ

> LLM-ᎯᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ ᎠᏍᏗᏍᏓᏅ (Claude Code, Cursor, ᏣᏥ ᏗᏍᏗᏍᏓᏅ).

## ᎡᏉ ᏤᎦ CLI ᎯᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ ᎠᏍᏗᏍᏓᏅ

* **JSON ᏗᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ.** `--json` ᎯᎪᏢ JSON ᏗᏍᏗᏍᏓᏅ ᎯᏍᏗᏍᏓᏅ stdout-Ꭱ ᏣᏥ
  *ᎯᎪᏢ JSON ᏗᏍᏗᏍᏓᏅ* — ᎦᏍᏗ progress-ᏗᏍᏗᏍᏓᏅ, ᎦᏍᏗ spinner. ᏗᏍᏗᏍᏓᏅ stderr-Ꭱ ᎡᏍᏗ
  `{"error": "...", "detail": "..."}` ᎯᏍᏗᏍᏓᏅ.
* **ᎯᏍᏗᏍᏓᏅ ᎠᏍᏗᏍᏓᏅ code.** `0` ᎠᏍᏗ / `1` ᎯᏍᏗᏍᏓᏅ / `2` auth / `3` server /
  `4` rate-ᏗᏍᏗᏍᏓᏅ / `5` ᎦᏍᏗ ᎯᏍᏗᏍᏓᏅ. ᏗᏍᏗᏍᏓᏅ ᎠᏍᏗᏍᏓᏅ ᎡᏍᏗ ᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ
  ᏗᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ ᎯᏍᏗᏍᏓᏅ.
* **ᎦᏍᏗ interactive prompt headless-ᏗᏍᏗᏍᏓᏅ.** `--yes` (ᏍᏗ `-y`) ᎯᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ
  command; `--api-key` ᏍᏗ `OMI_API_KEY` ᎯᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ interactive login.
* **ᏗᏍᏗᏍᏓᏅ retry ᏗᏍᏗᏍᏓᏅ.** `429` ᏍᏗ `5xx` ᏗᏍᏗᏍᏓᏅ backoff ᎯᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ.

## Auth (ᎯᎦᏍᏗ ᎯᏍᏗᏍᏓᏅ, ᏗᏍᏗᏍᏓᏅ)

ᏗᏍᏗᏍᏓᏅ ᎯᎪᏢ dev API key Omi web app-Ꭱ
(`https://app.omi.me` → Developer → API Keys) ᏍᏗ ᎯᎦᏍᏗ:

```bash
omi auth login                          # interactive paste; key ᎦᏍᏗ shell history-Ꭱ
# ᏍᏗ
export OMI_API_KEY=omi_dev_...          # ephemeral, container-ᏗᏍᏗᏍᏓᏅ
```

## ᏗᏍᏗᏍᏓᏅ ᎠᏍᏗ ᏗᏍᏗᏍᏓᏅ ᎤᏍᏗᏍᏓᏅ

### 1. ᏗᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ᏗᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ᏗᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ᏗᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ

```bash
omi action-item list --json --open
```

### 5. ᏗᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Omi Desktop-Ꭱ ᎯᎪᏢ ᎯᏍᏗᏍᏓᏅ local API, ᏗᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ ᎡᏍᏗ ᎦᏍᏗ
on-device screen history, recap, SQL, ᏍᏗ task ᎯᏍᏗᏍᏓᏅ cloud dev API-ᏗᏍᏗᏍᏓᏅ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ᏍᏗ, ephemeral session-ᏗᏍᏗᏍᏓᏅ:
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

ᎯᎦᏍᏗ ᏍᏗ delete ᏗᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ ᎯᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ᎯᏍᏗᏍᏓᏅ screenshot disk-Ꭱ
ᏍᏗ ᎠᏍᏗ stdout-Ꭱ JSON ᎯᏍᏗᏍᏓᏅ script-ᏗᏍᏗᏍᏓᏅ. ᏗᏍᏗᏍᏓᏅ screenshot ID
ᎠᏍᏗ `local search-screen` ᏍᏗ SQL `screenshots` table-Ꭱ. Desktop-Ꭱ ᎯᎪᏢ
structured failure `screenshot_pending`, `screenshot_file_missing`, ᏍᏗ
`screenshot_chunk_corrupted` ᎯᏍᏗᏍᏓᏅ, JSON mode-Ꭱ ᎯᎪᏢ `reason`, `hint`,
ᏍᏗ `screenshot_id` stderr-Ꭱ ᎡᏍᏗ ᏗᏍᏗᏍᏓᏅ ᎡᏍᏗ retry ᎯᎦᏍᏗ ID ᏍᏗ
report ᎯᎦᏍᏗ blocker. Validate ᎠᏍᏗ output `file PATH` ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ
vision tool-ᏗᏍᏗᏍᏓᏅ.

## ᎯᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ: Python ᏗᏍᏗᏍᏓᏅ loop

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

## ᏗᏍᏗᏍᏓᏅ ᎯᎦᏍᏗ rate limit

Memory: 120/hr. Conversation: 25/hr. Batch create: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ᏗᏍᏗᏍᏓᏅ ᎠᏍᏗ

* ᎯᏍᏗᏍᏓᏅ `--profile <name>` ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ ᏗᏍᏗᏍᏓᏅ Omi account ᏗᏍᏗᏍᏓᏅ.
  ᎯᎦᏍᏗ profile-Ꭱ ᏣᏥ credential ᏍᏗ API base.
* ᎯᏍᏗᏍᏓᏅ `--api-base http://localhost:8080` local backend testing-ᏗᏍᏗᏍᏓᏅ.
* ᎯᏍᏗᏍᏓᏅ `OMI_LOCAL_API_URL` ᏍᏗ `OMI_LOCAL_TOKEN` ᎯᎦᏍᏗ ᏗᏍᏗᏍᏓᏅ
  profile-local Desktop API setting ᎯᎦᏍᏗ run.
* ᎯᏍᏗᏍᏓᏅ `--verbose` debug-ᏗᏍᏗᏍᏓᏅ — ᎯᎪᏢ `METHOD path → status (Ns)`
  stderr-Ꭱ ᎦᏍᏗ stdout-ᏗᏍᏗᏍᏓᏅ, ᎡᏍᏗ JSON mode ᎠᏍᏗ valid.
* ᏗᏍᏗᏍᏓᏅ content ᎯᎦᏍᏗ conversation-ᏗᏍᏗᏍᏓᏅ, ᎯᏍᏗᏍᏓᏅ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
