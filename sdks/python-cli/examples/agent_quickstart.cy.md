# omi-cli ar gyfer asiantau

> Canllaw ymarferol ar gyfer fframweithiau wedi'u gyrru gan LLM (Claude Code, Cursor, eich botiau eich hun).

## Pam mae'r CLI yn gyfeillgar i asiantau

* **Cytundeb JSON sefydlog.** Mae `--json` yn allyrru dogfen JSON ddilys i stdout ac
  *yn unig* dogfen JSON — dim negeseuon cynnydd, dim troellwyr. Mae gwallau'n mynd i
  stderr fel `{"error": "...", "detail": "..."}`.
* **Codau gadael sefydlog.** `0` iawn / `1` defnydd / `2` dilysu / `3` gweinydd / `4` cyfyngiad
  cyfradd / `5` heb ei ganfod. Gall asiantau gangen ar y rhain heb ddosrannu
  gwallau iaith naturiol.
* **Dim anogwyr rhyngweithiol mewn cyd-destunau di-ben.** Pasio `--yes` (neu `-y`) i
  orchmynion dinistriol; pasio `--api-key` neu osod `OMI_API_KEY` i hepgor
  mewngofnodi rhyngweithiol.
* **Ymddygiad ailgynnig maddeugar.** Mae `429` a `5xx` yn cael eu hailgynnig gydag
  arafu graddol cyn dod i'r wyneb.

## Dilysu (un-amser, gan y bod dynol)

Mae'r defnyddiwr yn cael allwedd API datblygwr o ap gwe Omi
(`https://app.omi.me` → Developer → API Keys) a naill ai:

```bash
omi auth login                          # gludo rhyngweithiol; allwedd ddim yn hanes y gragen
# neu
export OMI_API_KEY=omi_dev_...          # byrhoedlog, cyfeillgar i gynwysyddion
```

## Y pum peth y mae asiantau yn eu gwneud amlaf

### 1. Darllen atgofion

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creu atgof

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Darllen sgyrsiau

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Darllen eitemau gweithredu agored

```bash
omi action-item list --json --open
```

### 5. Marcio eitem weithredu fel un wedi'i chwblhau

```bash
omi action-item complete --json a1b2c3d4
```

## API Penbwrdd Lleol

Pan fydd Omi Desktop yn datgelu ei API lleol, gall asiantau ymholi hanes sgrin
ar-ddyfais, ail-adroddiadau, SQL, a thasgau heb ddefnyddio API datblygwr y cwmwl:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# neu, ar gyfer sesiynau byrhoedlog:
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

Dim ond cwblhau neu ddileu tasgau pan fydd y defnyddiwr yn gofyn yn glir:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Mae `omi local screenshot SCREENSHOT_ID --output PATH` yn ysgrifennu'r ciplun sgrin i'r
ddisg ac yn dal i argraffu JSON i stdout ar gyfer sgriptiau. Mae ID y ciplun fel arfer
yn dod o `local search-screen` neu SQL dros y tabl `screenshots`. Os yw Desktop
yn dychwelyd methiant strwythuredig megis `screenshot_pending`, `screenshot_file_missing`,
neu `screenshot_chunk_corrupted`, mae modd JSON yn cadw'r meysydd `reason`, `hint`, ac
`screenshot_id` ar stderr fel y gall asiantau ailgynnig ID hŷn neu adrodd yr union
rwystr. Dilyswch allbynnau llwyddiannus gyda `file PATH` cyn eu pasio i offer gweledigaeth.

## Enghraifft weithredol: dolen asiant Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Galw'r CLI omi yn y modd JSON, gan godi eithriad ar godau gadael di-lwyddiant."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Mae'r CLI yn argraffu gwallau strwythuredig i stderr yn y modd JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Darllen pob eitem weithredu agored a marcio unrhyw beth hŷn na 30 diwrnod yn gyflawn.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ymdrin â chyfyngiadau cyfradd

Atgofion: 120/awr. Sgyrsiau: 25/awr. Creu mewn swp: 15/awr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # cyfyngiad cyfradd wedi'i gyrraedd
    err = json.loads(result.stderr)
    # mae err["detail"] yn edrych fel: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Awgrymiadau

* Defnyddiwch `--profile <enw>` os yw eich asiant yn rheoli nifer o gyfrifon Omi. Mae gan bob
  proffil ei fanylion dilysu a sylfaen API ei hun.
* Defnyddiwch `--api-base http://localhost:8080` ar gyfer profi backend lleol.
* Defnyddiwch `OMI_LOCAL_API_URL` ac `OMI_LOCAL_TOKEN` i ddiystyru gosodiadau API Desktop
  lleol-i-broffil ar gyfer un rhediad.
* Defnyddiwch `--verbose` ar gyfer dadfygio — mae'n logio `METHOD path → status (Ns)` i stderr
  heb effeithio ar stdout, felly mae'r modd JSON yn aros yn ddilys.
* Ar gyfer pibellu cynnwys i mewn i sgwrs, defnyddiwch `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
