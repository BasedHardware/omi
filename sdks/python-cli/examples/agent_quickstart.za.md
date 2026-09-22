# Aen omi-cli hawj agent

> Saw swhsuek hawj gij harness LLM daeuz dawh (Claude Code, Cursor, roxnaeuz bot mwngz gueh).

## Vihgyax aen CLI neix hab agent

* **Aen JSON dinghgen.** `--json` couh ok aen JSON wenz habfat youq stdout,
  *dan* aen JSON wenz — mbouj miz vah progressing, mbouj miz spinner. Aen coz
  bae stderr dwg `{"error": "...", "detail": "..."}`.
* **Aen exit code dinghgen.** `0` ndei / `1` yungh loengz / `2` auth loengz /
  `3` server loengz / `4` rate limited / `5` mbouj raen. Agent mbouj yungh
  fanhceh aen vah coz, ciuq aen code neix faenghij couh ndaej.
* **Youq aen headless mbouj miz aen cam.** Aen command sujhoaih, hawj `--yes`
  (roxnaeuz `-y`); hawj `--api-key` roxnaeuz cug `OMI_API_KEY` couh mbouj yungh
  daenghluk.
* **Aen retry gyangyauz.** `429` caeuq `5xx` couh daj backoff retry gonq, le
  ndaej okdaeuj.

## Auth (yungh boux guh daih'it baez)

Aen yungh youq Omi web app (`https://app.omi.me` → Developer → API Keys)
ndaej aen developer API key, le guh aen roxnaeuz aen:

```bash
omi auth login                          # dienz haeujbae; key mbouj youq shell lizsij
# roxnaeuz
export OMI_API_KEY=omi_dev_...          # aen ciapq, hab container
```

## Haj aen agent gueh lai

### 1. Yawj memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Guh aen memory moq

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Yawj conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Yawj aen action items lij haij

```bash
omi action-item list --json --open
```

### 5. Aen action item gaij liux

```bash
omi action-item complete --json a1b2c3d4
```

## Aen bendeiz Desktop API

Danghnaeuz Omi Desktop ok aen bendeiz API, agent mbouj yungh aen cloud dev API,
couh ndaej cam aen dennauj gwnz pinzmuz lizsij, recap, SQL, caeuq aen tasks:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# roxnaeuz, aen ciapq yungh:
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

Dan mwngz yawj haujlai, ndaej liux roxnaeuz suj aen task:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` couh sij aen screenshot
youq disk, lij ok JSON youq stdout hawj script. Aen screenshot ID daeuj daj
`local search-screen` roxnaeuz SQL youq aen `screenshots` biauj. Danghnaeuz
Desktop ok aen loengz `screenshot_pending`、`screenshot_file_missing`、
roxnaeuz `screenshot_chunk_corrupted`, JSON mode couh cug `reason`、`hint`、
caeuq `screenshot_id` youq stderr, agent ndaej retry aen ID gaeuq roxnaeuz
vah aen gep coj. Aen ndei suk'ok, yungh `file PATH` gonq, le ndaej hawj vision
tool.

## Aen laih: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Yungh JSON mode heuh aen omi CLI, exit code mbouj 0 couh gveq."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # JSON mode ndawde CLI couh ok aen coz youq stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Yawj aen action items lij haij, aen gvaq 30 ngoenz gaij liux.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Aen rate limit guh baenzlawz

Memories: aen cungduj 120 baez. Conversations: aen cungduj 25 baez. Aen doxdoengz guh: aen cungduj 15 baez.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] dwg aen: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aen dij lumj

* Danghnaeuz agent mwngz gvanj lai Omi account, yungh `--profile <name>`.
  Aen profile miz aen credentials caeuq API base gaeq.
* Aen bendeiz backend yungh `--api-base http://localhost:8080`.
* Yungh `OMI_LOCAL_API_URL` caeuq `OMI_LOCAL_TOKEN`, ndaej gaij aen profile
  ndawde Desktop API swzdin dan baez.
* Debug yungh `--verbose` — de sij `METHOD path → status (Ns)` youq stderr,
  mbouj baez stdout, JSON mode lij ndei.
* Yungh hawj aen saeb haeuj conversation, yungh `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
