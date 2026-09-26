# omi-cli do ghníomhairí (Gaeilge)

> Treoir phraiticiúil do chórais LLM (Claude Code, Cursor, do bhotaí féin).

## Cén fáth a bhfuil an CLI seo oiriúnach do ghníomhairí

* **Conradh JSON cobhsaí.** Ní tháirgeann `--json` ach doiciméad JSON bailí chuig stdout amháin — gan teachtaireachtaí dul chun cinn ná seachmalloirí (spinners). Seoltar earráidí chuig stderr mar `{"error": "...", "detail": "..."}`.
* **Cóid scoir chobhsaí.** `0` ceart go leor / `1` earráid úsáide / `2` fíordheimhniú / `3` earráid freastalaí / `4` teorainn ráta (rate limited) / `5` gan aimsiú. Is féidir le gníomhairí craobhú a dhéanamh ar na cóid seo gan teachtaireachtaí teanga nádúrtha a pharsáil.
* **Gan leideanna idirghníomhacha i gcomhthéacsanna headless.** Cuir `--yes` (nó `-y`) le horduithe millteacha; cuir `--api-key` nó socraigh `OMI_API_KEY` chun logáil isteach idirghníomhach a sheachaint.
* **Iompar atriallta trócaireach.** Déantar atriall le cúlú ar `429` agus `5xx` sula dtaispeántar an earráid don úsáideoir.

## Fíordheimhniú (aon uair amháin, ag an duine)

Faigheann an t-úsáideoir eochair API forbróra ón aip gréasáin Omi (`https://app.omi.me` → Developer → API Keys) agus socraíonn sé í:

```bash
omi auth login                          # greamú idirghníomhach; ní shábháiltear an eochair i stair an bhlaoisc
# nó
export OMI_API_KEY=omi_dev_...          # sealadach, oiriúnach do choimeádáin (Docker)
```

## Na cúig rud is mó a dhéanann gníomhairí

### 1. Cuimhní a léamh

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cuimhne a chruthú

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Comhráite a léamh

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Gníomhartha oscailte a léamh

```bash
omi action-item list --json --open
```

### 5. Gníomh a mharcáil mar críochnaithe

```bash
omi action-item complete --json a1b2c3d4
```

## API Deisce Áitiúil (Local Desktop API)

Nuair a chuireann Omi Desktop a API áitiúil ar fáil, is féidir le gníomhairí stair scáileáin, athbhreithnithe, SQL agus tascanna ar an ngléas a cheistiú gan an API forbróra néil a úsáid:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# nó le haghaidh seisiúin shealadacha:
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

Ná críochnaigh ná scrios tascanna ach amháin nuair a iarrann an t-úsáideoir go soiléir é:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Scríobhann `omi local screenshot SCREENSHOT_ID --output PATH` an gabháil scáileáin chuig an diosca agus clóbhuaileann sé JSON chuig stdout le haghaidh scripteanna. Is gnách go dtagann aitheantas an ghrianghraif scáileáin ó `local search-screen` nó ó cheist SQL thar an tábla `screenshots`. Má thugann Desktop teip struchtúrtha ar ais (amhail `screenshot_pending`, `screenshot_file_missing` nó `screenshot_chunk_corrupted`), caomhnaíonn mód JSON na réimsí `reason`, `hint` agus `screenshot_id` ar stderr ionas gur féidir le gníomhairí iarracht a dhéanamh ar shean-ID nó an bacainn bheacht a thuairisciú. Déan bailíochtú ar aschuir rathúla le `file PATH` sula gcuirtear ar aghaidh chuig uirlisí físe iad.

## Sampla oibrithe: Lúb ghníomhaire Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Glaoigh ar an CLI omi i mód JSON, ag ardú eisceachta ar chóid scoir neamhratha."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Clóbhuaileann an CLI earráidí struchtúrtha chuig stderr i mód JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"Scoir omi le cód {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Léigh gach gníomh oscailte agus marcáil aon cheann níos sine ná 30 lá mar críochnaithe.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Láimhseáil teorainneacha ráta (Rate Limits)

Cuimhní: 120/uair. Comhráite: 25/uair. Cruthuithe baisce: 15/uair.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # teorainn ráta sroichte
    err = json.loads(result.stderr)
    # breathnaíonn err["detail"] mar: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Leideanna

* Úsáid `--profile <ainm>` má bhíonn ilchuntais Omi á mbainistiú ag do ghníomhaire. Tá a dhintiúir agus a bhunáit API féin ag gach próifíl.
* Úsáid `--api-base http://localhost:8080` le haghaidh tástála cúil áitiúil.
* Úsáid `OMI_LOCAL_API_URL` agus `OMI_LOCAL_TOKEN` chun socruithe API Deisce na próifíle áitiúla a shárú le haghaidh rith amháin.
* Úsáid `--verbose` le haghaidh dífhabhtaithe — logálann sé `METHOD cosán → stádas (Ns)` chuig stderr gan cur isteach ar stdout, ionas go bhfanann mód JSON bailí.
* Chun ábhar a phíobáil isteach i gcomhrá, úsáid `--text -`:
  ```bash
  cat nótaí_cruinnithe.md | omi conversation create --text - --text-source other_text
  ```
