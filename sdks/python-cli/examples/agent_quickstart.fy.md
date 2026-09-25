# omi-cli foar aginten

> Praktyske gids foar LLM-oandreaune harnesses (Claude Code, Cursor, dyn eigen bots).

## Wêrom't de CLI agintfreonlik is

* **Stabyl JSON-kontrakt.** `--json` stjoert in jildich JSON-dokumint nei stdout
  en *allinnich* in JSON-dokumint — gjin fuortgongsberjochten, gjin spinners.
  Flaters geane nei stderr as `{"error": "...", "detail": "..."}`.
* **Stabile ôfslútkoades.** `0` ok / `1` gebrûk / `2` autentikaasje / `3`
  tsjinner / `4` taryflimite / `5` net fûn. Aginten kinne hjir op fertakje
  sûnder flaters yn natuerlike taal te parsen.
* **Gjin ynteraktive prompts yn headless-konteksten.** Jout `--yes` (of `-y`)
  mei oan destruktive kommando's; jout `--api-key` of set `OMI_API_KEY` om
  ynteraktive oanmelding oer te slaan.
* **Fertochsume weryntriedgedrach.** `429` en `5xx` wurde mei exponinsjele
  fertraging opnij besocht foardat se trochkomme.

## Autentikaasje (ien kear, troch de minske)

De brûker krijt in dev-API-kaai fan 'e Omi-webapp
(`https://app.omi.me` → Developer → API Keys) en dan ien fan beide:

```bash
omi auth login                          # ynteraktyf plakke; kaai komt net yn 'e shell-skiednis
# of
export OMI_API_KEY=omi_dev_...          # efemear, kontenerfreonlik
```

## De fiif dingen dy't aginten it meast dogge

### 1. Unthâlden lêze

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. In ûnthâld oanmeitsje

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Konversaasjes lêze

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Iepen aksje-items lêze

```bash
omi action-item list --json --open
```

### 5. In aksje-item as dien markearje

```bash
omi action-item complete --json a1b2c3d4
```

## Lokale Desktop-API

As Omi Desktop syn lokale API eksposearret, kinne aginten skermskiednis,
gearfettings, SQL en taken op it apparaat opfreegje sûnder de cloud-dev-API te
brûken:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# of, foar efemere sesjes:
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

Foltôgje of wiskje taken allinnich as de brûker dat dúdlik freget:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skriuwt de skermôfbylding
nei skiif en prints noch altyd JSON nei stdout foar scripts. It
skermôfbyldings-ID komt meastentiids fan `local search-screen` of SQL oer de
`screenshots`-tabel. As Desktop in strukturearre mislearring weromjout lykas
`screenshot_pending`, `screenshot_file_missing` of `screenshot_chunk_corrupted`,
behâldt de JSON-modus de fjilden `reason`, `hint` en `screenshot_id` op stderr,
sadat aginten in âlder ID opnij probearje kinne of it krekte blok sizze kinne.
Falidearje súksesfolle útkomsten mei `file PATH` foardat jo se nei vision-ark
stjoere.

## Utwurke foarbyld: Python-agintlûs

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Rop de omi CLI oan yn JSON-modus, en smyt by net-slagge ôfslútkoades."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # De CLI stjoert strukturearre flaters nei stderr yn JSON-modus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lês alle iepen aksje-items en markearje alles âlder as 30 dagen as foltôge.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Taryflimiten ôfhandelje

Unthâlden: 120/oere. Konversaasjes: 25/oere. Batch-oanmeitsjen: 15/oere.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # taryflimite
    err = json.loads(result.stderr)
    # err["detail"] sjocht der sa út: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Brûk `--profile <name>` as dyn agint mei meardere Omi-akkounts omgiet. Elk
  profyl hat syn eigen credential en API-basis.
* Brûk `--api-base http://localhost:8080` foar it testen fan 'e lokale backend.
* Brûk `OMI_LOCAL_API_URL` en `OMI_LOCAL_TOKEN` om de lokale
  Desktop-API-ynstellingen fan in profyl foar ien run te oerskriuwen.
* Brûk `--verbose` foar debuggen — it logt `METHOD path → status (Ns)` nei
  stderr sûnder stdout te beynfloedzjen, sadat JSON-modus jildich bliuwt.
* Om ynhâld yn in konversaasje te pipen, brûk `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
