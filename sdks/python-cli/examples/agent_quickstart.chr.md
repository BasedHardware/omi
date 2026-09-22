# omi-cli ᎢᎬᏱ ᏗᏅᏧᏗᏍᏗ ᎤᏙᏢᏒᎢ

> ᎢᎬᏱ ᏗᏅᏧᏗᏍᏗ ᎤᏙᏢᏒ ᎠᏓᏅᏖᏗᎸᏉᏗ ᎤᎾᏚᏗᏍᎬᎢ (Claude Code, Cursor, ᏂᏗᎨᏒ ᏂᏙᏓᏂ ᏗᏅᏧᏗᏍᏗ).

## CLI ᎾᏍᎩ ᏱᎬᎾᏍᏗᏍᎩᏍᏗᎢ ᎤᎾᏚᏗᏍᎬᎢ ᎾᏍᎩ ᎨᏒᎢ

* **JSON ᎤᏃᎮᏍᏗ ᎤᏰᎸᏗ.** `--json` stdout ᎤᏃᎮᏍᏗ ᏂᎦᎥ ᎤᏰᎸᏗ JSON ᎤᏃᎮᏍᏗ
  *JSON* ᎤᏃᎮᏍᏗ ᎤᏰᎸᏗ — ᎠᎾᎵᏍᏓᏗᏍᏗ ᏂᎦᎥ, spinner ᏂᎦᎥ. ᎠᏓᏅᏖᏗᎸᏉᏗ
  stderr ᎤᏃᎮᏍᏗ `{"error": "...", "detail": "..."}`.
* **Exit codes ᎤᏰᎸᏗ.** `0` ᎠᎾᎵᏍᏓᏗᏍᏗ / `1` ᎠᏎᎸᏗ / `2` ᎠᏓᏅᏖᏗᎸᏗ / `3` server / `4` rate
  limited / `5` ᏂᎨᏒᎾ. ᏱᎬᎾᏍᏗᏍᎩᏍᏗᎢ ᎾᏍᎩ ᎤᏰᏛᏗ ᏱᎩ ᎤᎾᎵᏍᏓᏗᏍᏗ
  natural-language ᎠᏓᏅᏖᏗᎸᏉᏗᎢ ᏱᎩ ᎾᏍᎩ ᎤᎾᏚᏗᏍᎬᎢ.
* **Headless ᎤᏃᎮᏍᏗ ᎤᎾᏚᏗᏍᎬᎢ ᎾᏍᎩ ᏂᎦᎥ.** ᎠᏓᏅᏖᏗᎸᏉᏗ ᎤᏙᏢᏒᎢ ᎤᎾᏚᏗᏍᎬᎢ
  `--yes` (`-y` ᏱᎩ); `--api-key` ᏱᎩ `OMI_API_KEY` ᏫᎦ
  interactive login ᎤᎾᏚᏗᏍᎬᎢ.
* **Retry ᎤᏰᎸᏗ ᎠᎾᎵᏍᏓᏗᏍᏗ.** `429` ᎠᎴ `5xx` ᎤᎾᏚᏗᏍᎬᎢ backoff
  ᎤᎾᏚᏗᏍᎬᎢ ᎾᏍᎩ ᎤᏰᏛᏗ ᏱᎩ.

## Auth (ᏌᏊ, ᎠᏓᏅᏗᎸᏙᏗ ᎠᏆᏓᎴᏍᏗᎢ)

ᏗᏏᎾᏒᏍᏗ ᎠᏎᎸᏉᏗ ᎠᏓᏅᏖᏗᎸᏉᏗᎢ `https://app.omi.me` → Developer → API Keys
API key ᎠᏆᏓᎴᏍᏗ ᎠᎴ ᎾᏍᎩ:

```bash
omi auth login                          # interactive paste; shell history ᎤᏃᎮᏍᏗ ᎤᏰᎸᏗ ᏂᎨᏒᎾ
# ᏱᎩ
export OMI_API_KEY=omi_dev_...          # ᎤᎾᏚᏗᏍᎬᎢ, container ᎠᏎᎸᏉᏗ
```

## ᏗᏅᏧᏗᏍᏗ ᎠᏎᎸᏉᏗ ᎤᎾᏚᏗᏍᎬᎢ ᎠᏎᎸᏗ

### 1. ᏗᎦᏁᏟᏗ ᎭᏫᎾᏗᏍᏗ

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. ᏗᎦᏁᏟᏗ ᎠᏚᏓᎴᏍᏗ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ᏗᎵᏃᎮᏗ ᎭᏫᎾᏗᏍᏗ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ᏗᎸᏫᏍᏓᏁᏗ ᎤᏰᏛᏗ ᏗᎸᏫᏍᏓᏁᏗ

```bash
omi action-item list --json --open
```

### 5. ᏗᎸᏫᏍᏓᏁᏗ ᎠᏎᎸᏗ

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Omi Desktop local API ᎤᎾᏚᏗᏍᎬᎢ, ᏱᎬᎾᏍᏗᏍᎩᏍᏗᎢ screen history, recaps, SQL ᎠᎴ tasks
cloud dev API ᏂᎨᏒᎾ ᎠᏆᏓᎴᏍᏗᎢ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ᏱᎩ, ephemeral sessions:
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

ᏗᏏᎾᏒᏍᏗ ᎠᏓᏅᏗᎸᏙᏗ ᎠᏆᏓᎴᏍᏗᎢ ᎤᎾᏚᏗᏍᎬᎢ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` screenshot ᎠᏆᏓᎴᏍᏗ
file ᎤᏃᎮᏍᏗ JSON stdout ᎤᏃᎮᏍᏗ scripts. Screenshot ID
`local search-screen` ᏱᎩ SQL `screenshots` table ᎤᏃᎮᏍᏗ. Desktop
`screenshot_pending`, `screenshot_file_missing`,
`screenshot_chunk_corrupted` structured failure ᎤᎾᏚᏗᏍᎬᎢ, JSON mode
`reason`, `hint`, `screenshot_id` fields stderr ᎤᏃᎮᏗ
ᏱᎬᎾᏍᏗᏍᎩᏍᏗᎢ older ID ᎤᎾᏚᏗᏍᎬᎢ ᏱᎩ exact blocker ᎤᎾᏚᏗᏍᎬᎢ.
Successful outputs `file PATH` ᎤᎾᏚᏗᏍᎬᎢ vision tools
ᏱᎩ.

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

## Rate limits ᎠᏎᎸᏗ

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ᎤᏰᎸᏗ

* `--profile <name>` ᎤᎾᏚᏗᏍᎬᎢ ᏱᎬᎾᏍᏗᏍᎩᏍᏗᎢ multiple Omi accounts
  ᎤᎾᏚᏗᏍᎬᎢ. ᎤᏙᏢᏒᎢ ᎤᏃᎮᏍᏗ credential ᎠᎴ API base.
* `--api-base http://localhost:8080` local backend testing.
* `OMI_LOCAL_API_URL` ᎠᎴ `OMI_LOCAL_TOKEN` profile-local
  Desktop API ᎤᏰᎸᏗ one run ᎤᎾᏚᏗᏍᎬᎢ.
* `--verbose` debugging `METHOD path → status (Ns)` stderr
  stdout ᏂᎨᏒᎾ, JSON mode ᎤᏰᎸᏗ.
* Conversation ᎠᏆᏓᎴᏍᏗ content pipe, `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
