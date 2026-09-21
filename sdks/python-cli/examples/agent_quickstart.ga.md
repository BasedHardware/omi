# omi-cli do ghníomhairí AI

> Treoir phraiticiúil do thimpeallachtaí faoi thiomáint LLM (Claude Code, Cursor, do bhotaí féin).

## Cén fáth a bhfuil an CLI cairdiúil do ghníomhairí

* **Conradh cobhsaí JSON.** Aistríonn `--json` cáipéis bhailí JSON go stdout agus
  *ach* cáipéis JSON amháin — gan teachtaireachtaí dul chun cinn, gan rothaí casachta. Téann earráidí go
  stderr mar `{"error": "...", "detail": "..."}`.
* **Cóid fágála cobhsaí.** `0` ceart / `1` úsáid / `2` fíordheimhniú / `3` freastalaí / `4` teorainn
  ráta / `5` gan aimsiú. Is féidir le gníomhairí craobhú ar na cóid seo gan gá a bheith le hearráidí
  teanga nádúrtha a pharsáil.
* **Gan leideanna idirghníomhacha i gcomhthéacsanna gan ceann.** Cuir `--yes` (nó `-y`) le
  horduithe millteacha; cuir `--api-key` leis nó socraigh `OMI_API_KEY` chun logáil isteach
  idirghníomhach a sheachaint.
* **Iompar maithiúnach athiarrachta.** Déantar athiarracht ar `429` agus `5xx` le himeacht
  aimsire (backoff) sula léirítear an earráid.

## Fíordheimhniú (aonuaire, déanta ag an duine)

Faigheann an t-úsáideoir eochair API forbróra ón aip ghréasáin Omi
(`https://app.omi.me` → Developer → API Keys) agus déanann sé ceachtar díobh:

```bash
omi auth login                          # greamú idirghníomhach; eochair nach bhfuil i stair na blaaoisce
# nó
export OMI_API_KEY=omi_dev_...          # sealadach, cairdiúil do choimeádáin (containers)
```

## Na cúig rud is mó a dhéanann gníomhairí

### 1. Léigh cuimhní

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cruthaigh cuimhne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Léigh comhráite

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Léigh míreanna gníomhaíochta oscailte

```bash
omi action-item list --json --open
```

### 5. Marcáil mír ghníomhaíochta mar déanta

```bash
omi action-item complete --json a1b2c3d4
```

## API Deisce Áitiúil (Local Desktop API)

Nuair a nochtann Omi Desktop a API áitiúil, is féidir le gníomhairí stair scáileáin,
athbhreithnithe, SQL, agus tascanna ar an ngléas a fhiosrú gan úsáid a bhaint as API forbróra scamall:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# nó, do sheisiúin shealadacha:
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

Ná comhlánaigh nó scrios tascanna ach amháin nuair a iarrann an t-úsáideoir go soiléir é:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Scríobhann `omi local screenshot SCREENSHOT_ID --output PATH` an gabháil scáileáin go
diosca agus priontálann sé JSON go stdout fós do scripteanna. Tagann an t-aitheantas scáileáin
go hiondúil ó `local search-screen` nó SQL thar an tábla `screenshots`. Má thagann cliseadh
struchtúrtha ón Deasc ar nós `screenshot_pending`, `screenshot_file_missing`, nó
`screenshot_chunk_corrupted`, caomhnaíonn mód JSON na réimsí `reason`, `hint`, agus
`screenshot_id` ar stderr ionas gur féidir le gníomhairí triail a bhaint as seanaaitheantas
nó an fhadhb chruinn a thuairisciú. Déan bailíochtú ar aschuir rathúla le `file PATH` sula
seoltar chuig uirlisí fís iad.

## Sampla praiticiúil: Lúb ghníomhaire Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Glaoigh ar an omi CLI i mód JSON, ag ardú earráide ar chóid fágála neamhratha."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Priontálann an CLI earráidí struchtúrtha go stderr i mód JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi fágtha le {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Léigh gach mír ghníomhaíochta oscailte agus marcáil aon cheann níos sine ná 30 lá mar déanta.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Láimhseáil teorainneacha ráta

Cuimhní: 120/uair. Comhráite: 25/uair. Baiscchruthaithe: 15/uair.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # teorainn ráta (rate limited)
    err = json.loads(result.stderr)
    # breathnaíonn err["detail"] mar: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Leideanna

* Úsáid `--profile <ainm>` má láimhseálann do ghníomhaire cuntais Omi iolracha. Tá a
  dheimhniú agus a bhonn API féin ag gach próifíl.
* Úsáid `--api-base http://localhost:8080` le haghaidh tástála áitiúla cúil.
* Úsáid `OMI_LOCAL_API_URL` agus `OMI_LOCAL_TOKEN` chun socruithe API Deisce
  próifíle áitiúla a shárú d'aon rith amháin.
* Úsáid `--verbose` le haghaidh dífhabhtaithe — logálann sé `METHOD path → status (Ns)` go stderr
  gan cur isteach ar stdout, ionas go bhfanann mód JSON bailí.
* Chun ábhar a phíbáil isteach i gcomhrá, úsáid `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
