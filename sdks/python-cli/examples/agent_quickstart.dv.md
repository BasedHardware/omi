# އޭޖަންޓުންނަށް omi-cli

> LLM އިން ހުންނަ ހާނަސްތަކަށް ޕްރެކްޓިކަލް ގައިޑެއް (Claude Code, Cursor, ތިބާގެ އަމިއްލަ ބޮޓުން).

## CLI އޭޖަންޓުންނަށް ރަނގަޅު ވާ ސަބަބު

* **ސްޓޭބަލް JSON ކޮންޓްރެކްޓް.** `--json` އިން stdout އަށް ފޮނުވާނީ ވެލިޑް
  JSON ޑޮކިއުމަންޓެއް އަދި *ހަމަ* JSON ޑޮކިއުމަންޓެއް — ޕްރޮގްރެސް މެސޭޖުތައް
  ނެތް، ސްޕިނަރތައް ނެތެވެ. އެރަރތައް ވާނީ stderr އަށް
  `{"error": "...", "detail": "..."}` ގޮތުންނެވެ.
* **ސްޓޭބަލް އެގްޒިޓް ކޯޑްތައް.** `0` ok / `1` usage / `2` auth / `3` server /
  `4` rate limited / `5` not found. އޭޖަންޓުންނަށް މީގެ މައްޗަށް ބްރާންޗް
  ކުރެވޭނީ ނޭޗުރަލް ލެންގުއޭޖް އެރަރތައް ޕާސް ނުކުރެެއްޔާ އެވެ.
* **ހެޑްލެސް ކޮންޓެކްސްޓްތަކުގައި އިންޓަރެކްޓިވް ޕްރޮމްޕްޓްތައް ނެތް.**
  ޑިސްޓްރަކްޓިވް ކަމަންޑްތަކަށް `--yes` (ނުވަތަ `-y`) ޕާސް ކުރާށެވެ؛
  އިންޓަރެކްޓިވް ލޮގިން ސްކިޕް ކުރުމަށް `--api-key` ޕާސް ކުރާށެވެ ނުވަތަ
  `OMI_API_KEY` ސެޓް ކުރާށެވެ.
* **ފޯގިވިން ރީޓްރައި ބިހޭވިއަރ.** `429` އަދި `5xx` ދައްކަން ކުރިން ބެކްއޮފް
  އާއެކު ރީޓްރައި ކުރެވޭނެއެވެ.

## އޮތް (އެއް ފަހަރު، އިންސާނުން)

ޔޫސަރ އަށް Omi web app އިން (`https://app.omi.me` → Developer → API Keys)
dev API key އެއް ލިބޭނެއެވެ، އަދި ދެން މީގެ ތެރެއިން އެއް ކަމެއް ކުރާނެއެވެ:

```bash
omi auth login                          # އިންޓަރެކްޓިވްކޮށް ޕޭސްޓް؛ ކީ ޝެލް ހިސްޓަރީގައި ނުވެއެވެ
# ނުވަތަ
export OMI_API_KEY=omi_dev_...          # އެފިމެރަލް، ކޮންޓެއިނަރުންނަށް ރަނގަޅު
```

## އޭޖަންޓުން އެންމެ ގިނައިން ކުރާ ފަސް ކަންތައް

### 1. މެމޮރީސް ކިޔާލުން

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. މެމޮރީއެއް ބައްދަލުކުރުން

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. ކޮންވަރސޭޝަންސް ކިޔާލުން

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ހުޅުވާފައިވާ އެކްޝަން އައިޓަމްސް ކިޔާލުން

```bash
omi action-item list --json --open
```

### 5. އެކްޝަން އައިޓަމެއް ނިމުނު ކަމަށް މާކް ކުރުން

```bash
omi action-item complete --json a1b2c3d4
```

## ލޯކަލް ޑެސްކްޓޮޕް API

Omi Desktop އިން އޭގެ ލޯކަލް API އެކްސްޕޯޒް ކުރާއިރު، އޭޖަންޓުންނަށް ކްލައުޑް
dev API ބޭނުން ނުކުރެެއްޔާ އޮން-ޑިވައިސް ސްކްރީން ހިސްޓަރީ، ރިކެޕްސް، SQL،
އަދި ޓާސްކްތައް ކުއެރީ ކުރެވޭނެއެވެ:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ނުވަތަ، އެފިމެރަލް ސެޝަންތަކަށް:
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

ޔޫސަރ ސާފުކޮށް އެދޭ ހާލަތުގައި ހަމައެކަނި ޓާސްކްތައް ނިންމާށެވެ ނުވަތަ
ފޮހެލާށެވެ:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` އިން ސްކްރީންޝޮޓް ޑިސްކަށް
ލިޔޭނެ އަދި ސްކްރިޕްޓްތަކަށް JSON އިހެޔޮވެސް stdout އަށް ޕްރިންޓް ކުރާނެއެވެ.
ސްކްރީންޝޮޓް ID އާންމުކޮށް ލިބެނީ `local search-screen` އިން ނުވަތަ
`screenshots` ޓޭބަލް މައްޗަށް SQL އިންނެވެ. Desktop އިން `screenshot_pending`،
`screenshot_file_missing`، ނުވަތަ `screenshot_chunk_corrupted` ފަދަ
ސްޓްރަކްޗަރޑް ފެއިލިއުރެއް ރިޓާން ކުރިނަމަ، JSON މޯޑުގައި `reason`، `hint`،
އަދި `screenshot_id` ފީލްޑްތައް stderr ގައި ބެލެހެއްޓޭނީ އޭޖަންޓުންނަށް
ދުރާލަ ID އަކުން ރީޓްރައި ކުރެވޭނެ ނުވަތަ ސީދާ ބްލޮކަރ ރިޕޯޓް ކުރެވޭނެ
ގޮތަށެވެ. ވިޝަން ޓޫލްތަކަށް ފޮނުވަން ކުރިން ކާމިޔާބު އައުޓްޕުޓްތައް
`file PATH` އާއެކު ވެލިޑޭޓް ކުރާށެވެ.

## މަސައްކަތް ކޮށްފައިވާ މިސާލު: Python އޭޖަންޓް ލޫޕް

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI JSON މޯޑުގައި ކޯލް ކުރުން، ކާމިޔާބު ނުވާ އެގްޒިޓް ކޯޑްތަކުގައި އެރަރ ރޭޒް ކުރުން."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # JSON މޯޑުގައި CLI އިން ސްޓްރަކްޗަރޑް އެރަރތައް stderr އަށް ޕްރިންޓް ކުރާނެއެވެ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# ހުޅުވާފައިވާ ހުރިހާ އެކްޝަން އައިޓަމްތައް ކިޔާ، 30 ދުވަހަށް ވުރެ ދުރާލަ އެއްޗެސް ނިމުނު ކަމަށް މާކް ކުރާށެވެ.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ރޭޓް ލިމިޓްތައް ހެންޑަލް ކުރުން

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ރޭޓް ލިމިޓް
    err = json.loads(result.stderr)
    # err["detail"] ވާނީ މި ފަދައިން: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ޓިޕްސް

* ތިބާގެ އޭޖަންޓް ގިނަ Omi އެކައުންޓްތަކާއި މެދު މަސައްކަތް ކުރާނަމަ
  `--profile <ނަން>` ބޭނުންކުރާށެވެ. ކޮންމެ ޕްރޮފައިލެއްގައި އޭގެ އަމިއްލަ
  credential އަދި API base އެބަހުއްޓެވެ.
* ލޯކަލް ބެކެންޑް ޓެސްޓިންގަށް `--api-base http://localhost:8080`
  ބޭނުންކުރާށެވެ.
* އެއް ރަނެއްގައި ޕްރޮފައިލްގެ ލޯކަލް Desktop API ސެޓިންގްސް އޮވަރައިޓް
  ކުރުމަށް `OMI_LOCAL_API_URL` އަދި `OMI_LOCAL_TOKEN` ބޭނުންކުރާށެވެ.
* ޑިބަގިންގަށް `--verbose` ބޭނުންކުރާށެވެ — އެއީ `METHOD path → status (Ns)`
  stderr އަށް ލޮގް ކުރާނެ އެއްޗެއް، stdout އަށް އަތް ނުލާތީ، އޭގެ
  ނަތީޖާއަކަށް JSON މޯޑު ވެލިޑްކޮށް ދެމިއޮތޭނެއެވެ.
* ކޮންވަރސޭޝަނެއްގެ ތެރެއަށް ކޮންޓެންޓް ޕައިޕް ކުރުމަށް، `--text -`
  ބޭނުންކުރާށެވެ:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
