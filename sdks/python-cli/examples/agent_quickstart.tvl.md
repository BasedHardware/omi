# omi-cli mo gatai e konga

> Tau tusi fakamafa mo e gatai e LLM (Claude Code, Cursor, koe gatai e konga).

## Kehekehe CLI kehekehe mo gatai e konga

* **JSON contract fakamafa.** `--json` fakatulaga ha JSON monumo ki a stdout *ʻeaʻea* JSON monumo — ʻeaʻea ha fakamatala, ʻeaʻea ha spinner. ʻE fakatulaga ki a stderr `{"error": "...", "detail": "..."}`.
* **Exit code fakamafa.** `0` monumo / `1` amanogi / `2` auth / `3` server / `4` rate limited / `5` ʻeaʻia. Gatai e konga ʻia ʻia ʻeaʻia ʻia JSON contract.
* **ʻEʻe prompt fakatū ki a headless.** Fakatulaga `--yes` (pe `-y`) ki a komata fakatāpoe; fakatulaga `--api-key` pe `OMI_API_KEY` ke ʻeaʻia ha login fakatū.
* **Mafuaʻeʻe retry.** `429` a `5xx` ʻia fakatulaga retry mo e backoff kuaʻakiʻaki.

## Auth (fakatāʻu, mo e taoʻaki)

ʻE kumi ha API key dev ʻia Omi web app
(`https://app.omi.me` → Developer → API Keys) pe:

```bash
omi auth login                          # paste fakatū; key ʻeaʻia shell history
# pe
export OMI_API_KEY=omi_dev_...          # ephemeral, container
```

## ʻE lima nga ʻī ʻia e gatai e konga

### 1. Gahua memory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fakatulaga ha memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Gahua conversation

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Gahua action item

```bash
omi action-item list --json --open
```

### 5. Taukī ha action item monumo

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

ʻA Omi Desktop ʻia fakamafa ha local API, ʻe gatai e konga ʻia gahua screen history, recap, SQL mo e task ʻeaʻia ha cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# pe, ephemeral session:
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

Fakahouʻaki ha task ʻeaʻia ha talamalama tō:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` tohi screenshot ki a faili
a ʻia fakatulaga JSON ki a stdout mo e ʻī script. Screenshot ID ʻia
`local search-screen` pe SQL ʻia tabele `screenshots`. ʻA Omi Desktop ʻia fakatulaga ha fakaʻeahia mea
mea `screenshot_pending`, `screenshot_file_missing`,
pe `screenshot_chunk_corrupted`, ʻia JSON mode ʻia monumo fields `reason`, `hint`, pe
`screenshot_id` ki a stderr kia ʻe gatai e konga ʻia fakatulaga ha ID
tō pe ʻia fakatonuga ha mea monumo. Taukī ha output monumo `file PATH` kuaʻakiʻaki
ki a vision tool.

## Tauhaha: Python agent loop

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

## Gahua rate limit

Memory: 120/hr. Conversation: 25/hr. Batch create: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ʻĀfi

* Fakatulaga `--profile <name>` ʻa e gatai e konga haʻunga haʻunga Omi.
  Profile haʻunga ʻia ha credential a API base.
* Fakatulaga `--api-base http://localhost:8080` mo e local backend.
* Fakatulaga `OMI_LOCAL_API_URL` mo e `OMI_LOCAL_TOKEN` ke ʻeaʻia
  Desktop API mo e haʻunga gahua.
* Fakatulaga `--verbose` mo e ʻāfā — ʻia fakamafa `METHOD path → status (Ns)` ki a stderr
  ʻeaʻia ha stdout, JSON mode ʻia monumo.
* Fakatulaga ha content ki ha conversation, fakatulaga `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
