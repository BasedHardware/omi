# omi-cli guh vunz yungh dienznauj

> Saw neix guh duz vunz yungh dienznauj bae gongh (Claude Code, Cursor caeuq dienznauj youq ranz).

## Gijgiz mingzlingh ndei guh vunz yungh dienznauj

* **JSON ndei.** `--json` ndaej JSON ndei bae youq stdout, mbouj miz saw baenz. Saw youq ndeij bae youq stderr.
* **Code ok ndei.** `0` ndei / `1` yungh ndeij / `2` bae dauq ndeij / `3` gij ngangq ndeij / `4` caiq lai / `5` mbouj ndaej.
* **Mbouj ndaej boux vunz youq dienznauj ranz.** Caiq `--yes` guh mingzlingh youq ndeij; caiq `--api-key` aek daeuj damh `OMI_API_KEY`.
* **De roux youq laeng.** `429` caeuq `5xx` de youq laeng caiq le, caeuq ok ma.

## Bae dauq (it roeng, vunz bae dauq)

Vunz bae dauq [app.omi.me](https://app.omi.me), youq **Developer → API Keys** ndaej key, caeuq:
```bash
omi auth login                          # Damh key youq dienznauj, mbouj youq saw youq laeng
# aek daeuj
export OMI_API_KEY=omi_dev_...          # Yungh youq doenz neix
```

## Haj banghfaek vunz yungh dienznauj hoiz caiq

### 1. Roux vunz yiengh
```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Sai vunz yiengh
```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Roux daihvaq
```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Roux gongzdan youq ndeu
```bash
omi action-item list --json --open
```

### 5. Gongzdan bae ndaej laeuz
```bash
omi action-item complete --json a1b2c3d4
```

## API youq dienznauj

Dienznauj Omi miz API youq ranz, vunz yungh dienznauj roux saw youq dienznauj, mbouj bae youq gij ngangq youq baenz:
```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# Aek daeuj, yungh youq doenz neix:
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

Vunz gangj roux ndaej, caeuq sai gongzdan bae ndaej:
```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` damh saw youq dienznauj, caeuq ndaej JSON. ID youq `local search-screen` aek daeuj youq saw `screenshots` ndaej. Gij ngangq youq ndeij (`screenshot_pending`...), JSON mbouj laep `reason`, `hint` caeuq `screenshot_id`. Yungh `file PATH` yiemh gonq.
```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Caiq omi youq JSON, youq ndeij de ok ma."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Mingzlingh sai saw youq ndeij bae youq stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Roux gongzdan youq ndeu, gongzdan youq laeng 30 ngoenz sai de bae ndaej.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ndaej roux caiq lai

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.
```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # caiq lai
    err = json.loads(result.stderr)
    # `err["detail"]` dwg: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Saw ndaej roux

* Caiq `--profile <name>` vunz miz lai Omi. It profile miz key youq ranz.
* Caiq `--api-base http://localhost:8080` yiemh youq dienznauj ranz.
* Caiq `OMI_LOCAL_API_URL` caeuq `OMI_LOCAL_TOKEN` youq it roeng.
* Caiq `--verbose` yiemh saw youq ndeij.
* Sai saw bae dauq daihvaq, caiq `--text -`:
```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
