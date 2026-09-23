# omi-cli d'oireannaí

> Treoir phraiticiúil do harnaisí tiomáinte ag LLM (Claude Code, Cursor, do bhotaí féin).

## Cén fáth go bhfuil an CLI cairdiúil d'oibríochtaí

* **Comhartha JSON seasmhach.** `--json` aslonnaíonn doiciméad JSON bailí go dtí stdout agus
  *amháin* doiciméad JSON — gan teachtaireachtaí dul chun cinn, gan spinners. Téann earráidí go dtí
  stderr mar `{"error": "...", "detail": "..."}`.
* **Cóid imeachta seasmhacha.** `0` ok / `1` úsáid / `2` auth / `3` freastalaí / `4`
  teorainn ráta / `5` gan aimsiú. Is féidir le hoibríochtaí brainse bunaithe ar na c seo
  gan anailís a dhéanamh ar earráidí i nádúrtha.
* **Gan aiseanna idirghníomhacha i gcomhthéacsanna gan ceannaire.** Seachain `--yes` (nó `-y`)
  le haghaidh orduithe scriosacha; seachain `--api-key` nó socrú `OMI_API_KEY` chun an t-insteáil
  idirghníomhach a léim thar.
* **Iompar maithéineach ag athdheargadh.** Déantar `429` agus `5xx` a athdheargadh le backoff
  sula dtaispeántar iad.

## Auth (uair amháin, ag an duine)

Faigheann an t-úsáideoir eochair API forbartha ón aip gréasáin Omi
(`https://app.omi.me` → Developer → API Keys) agus ceann de dhá rud:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Na cúig ruda a dhéanann oibríochtaí is minice

### 1. Léigh cuimhneacháin

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cruthaigh cuimhneachán

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Léigh comhráite

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Léigh gníomhaíochtaí oscailte

```bash
omi action-item list --json --open
```

### 5. Marcáil gníomhaíocht mar críochnaithe

```bash
omi action-item complete --json a1b2c3d4
```

## API Deisce áitiúil

Nuair a nochtann Omi Desktop a API áitiúil, is féidir le hoibríochtaí ceist a chur ar
stair scáileáin an ghléis, athchúraim, SQL agus tascanna gan úsáid a bhaint as an API néil:

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

Cruthaigh nó scrios tascanna amháin nuair a iarrann an t-úsáideoir go soiléir:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Scríobann `omi local screenshot SCREENSHOT_ID --output PATH` an scáileán go dtí an diosca
agus fós aslonnaíonn JSON go dtí stdout do scripteanna. Tagann ID an scáileáin de ghnáth ó
`local search-screen` nó SQL thar an táiblé `screenshots`. Má thugann Desktop teip struchtúrtha
mar `screenshot_pending`, `screenshot_file_missing`, nó `screenshot_chunk_corrupted`,
coinníonn mód JSON na réitigh `reason`, `hint`, agus `screenshot_id` ar stderr ionas gur féidir
le hoibríochtaí ID níos sine a thriail nó an blocáil dhéanach a thuairisciú. Deimhnigh aschuir
rathúla le `file PATH` sula seolann tú iad chuig uirlisí vision.

## Sampla cleachtais: lúb oibrí Python

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

## Láimhseáil teorann ráta

Cuimhneacháin: 120/uair. Comhráite: 25/uair. Cruthú mais: 15/uair.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Leideanna

* Úsáid `--profile <ainm>` má riarann d'oibríóra cuntais Omi iolracha. Tá creidiúnacha
  agus API base féin ag gach próifíl.
* Úsáid `--api-base http://localhost:8080` le haghaidh tástáil backend áitiúil.
* Úsáid `OMI_LOCAL_API_URL` agus `OMI_LOCAL_TOKEN` chun socruithe Desktop API
  próifíle-áitiúla a chur ar leataobh le haghaidh rith amháin.
* Úsáid `--verbose` le haghaidh dífhabhtaithe — logálann sé `METHOD path → status (Ns)` go stderr
  gan tionchar a imirt ar stdout, mar sin fanann mód JSON bailí.
* Le haghaidh ábhair a chur isteach i gcomhrá, úsáid `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
