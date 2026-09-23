# omi-cli evit an oberourien

> Dornlevr pleustrek evit ar benvegoù renet gant LLM (Claude Code, Cursor, ho robotoù hoc'h-unan).

## Perak eo mignon an CLI d'an oberourien

* **Ur gevrat JSON stabil.** Skriv `--json` ur skrid JSON gwirion da stdout —
  *ur skrid JSON hepken* — hep kemennoù araokadur, hep spinner. Mont a ra ar
  fazioù da stderr evel `{"error": "...", "detail": "..."}`.
* **Kodoù mont er-maez stabil.** `0` mat / `1` implij / `2` gwiriekadur / `3`
  servijer / `4` bevennet an tizh / `5` nann kavet. Gall an oberourien rannañ
  war ar re-se hep dielfennañ fazioù yezh naturel.
* **Hep goulenn etreoberiat e kenarroud headless.** Ro `--yes` (pe `-y`) d'an
  urzhioù distrujus; ro `--api-key` pe laka `OMI_API_KEY` evit lammat ar
  c'hennaskañ etreoberiat.
* **Emzalc'h adverkañ damerzhus.** Adverket e vez `429` ha `5xx` gant backoff
  a-raok bezañ diskouezet.

## Gwiriekadur (ur wech, gant an den)

Kavout a ra an implijer un alc'hwez API dev eus ar goulev web Omi
(`https://app.omi.me` → Developer → API Keys) ha neuze dibab:

```bash
omi auth login                          # pegañ etreoberiat; n'emañ ket an alc'hwez en istor ar shell
# pe
export OMI_API_KEY=omi_dev_...          # berrbad, gouzañvus evit ar c'honteiner
```

## Ar pemp tra a reer ar muiañ gant an oberourien

### 1. Lenn ar memorioù

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Krouiñ ur memor

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lenn an divizoù

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lenn an oberoù digor

```bash
omi action-item list --json --open
```

### 5. Merkañ un ober evel graet

```bash
omi action-item complete --json a1b2c3d4
```

## API an Desktop Lec'hel

Pa ziskouez Omi Desktop e API lec'hel, gall an oberourien goulenn istor ar
skramm war an ardivink, diverradennoù, SQL, hag oberoù hep implijout API dev ar
goumoulenn:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# pe, evit sesionoù berrbad:
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

Na lak da benn pe na zilez ket an oberoù nemet pa c'houlenn an implijer sklaer:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Skriv `omi local screenshot SCREENSHOT_ID --output PATH` ar skrammadenn war ar
bladenn ha moullañ a ra JSON da stdout c'hoazh evit ar skriptoù. Dont a ra ID
ar skrammadenn peurliesañ eus `local search-screen` pe SQL war an daolenn
`screenshots`. Ma tistro Desktop ur fazi frammek evel `screenshot_pending`,
`screenshot_file_missing`, pe `screenshot_chunk_corrupted`, miret e vez gant ar
mod JSON ar maezioù `reason`, `hint`, ha `screenshot_id` war stderr evit ma
c'hellfe an oberourien adverkañ ur ID koshoc'h pe reiñ an harz resis. Gwiriit
an disoc'hoù mat gant `file PATH` a-raok o c'has da vinvioù gweled.

## Skouer labour: lank an oberour Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ober gant an CLI omi e mod JSON, o sevel ur fazi war kodoù mont er-maez c'hwitet."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Moullañ a ra an CLI fazioù frammek da stderr e mod JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lenn an holl oberoù digor ha merkañ kement tra koshoc'h eget 30 devezh evel graet.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Merañ ar vevennoù tizh

Memorioù: 120/eur. Divizoù: 25/eur. Krouidigezhioù a-vloc'had: 15/eur.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # tizh bevennet
    err = json.loads(result.stderr)
    # err["detail"] a zo evel: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tuoù-ali

* Grit gant `--profile <name>` ma vez ho oberour oc'h ober war-dro meur a gont
  Omi. Pep profil en deus e wiriekadur hag e API base dezhañ.
* Grit gant `--api-base http://localhost:8080` evit amprouiñ ur backend lec'hel.
* Grit gant `OMI_LOCAL_API_URL` hag `OMI_LOCAL_TOKEN` evit flastrañ arventennoù
  API Desktop ar profil evit ur redadenn.
* Grit gant `--verbose` evit an dibugerezh — kazetenn `METHOD path → status (Ns)` war stderr
  hep touchañ stdout, setu e chom ar mod JSON gwirion.
* Evit kas danvez d'ur gomzadenn gant ur pipe, grit gant `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
