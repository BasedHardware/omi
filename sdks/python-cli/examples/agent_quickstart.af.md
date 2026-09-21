# omi-cli vir agente

> Praktiese gids vir LLM-gedrewe hulpmiddele (Claude Code, Cursor, jou eie bots).

## Waarom die CLI agent-vriendelik is

* **Stabiele JSON-kontrak.** `--json` skryf 'n geldige JSON-dokument na stdout en
  *slegs* 'n JSON-dokument — geen vorderingsboodskappe of spinners nie. Foute gaan na
  stderr as `{"error": "...", "detail": "..."}`.
* **Stabiele uitgangskodes.** `0` reg / `1` gebruik / `2` verifikasie / `3` bediener / `4` tempo
  beperk / `5` nie gevind nie. Agente kan hierop vertak sonder om
  natuurliketaal-foute te ontleed.
* **Geen interaktiewe vrae in koplose kontekste nie.** Gee `--yes` (of `-y`) aan
  vernietigende opdragte; gee `--api-key` of stel `OMI_API_KEY` om
  interaktiewe aanmelding oor te slaan.
* **Verdraagsame herprobeergedrag.** `429` en `5xx` word met terughouding herprobeer
  voordat dit teruggegee word.

## Verifikasie (eenmalig, deur die mens)

Die gebruiker kry 'n ontwikkelaar-API-sleutel uit die Omi-webtoepassing
(`https://app.omi.me` → Developer → API Keys) en gebruik dan een van:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Die vyf dinge wat agente die meeste doen

### 1. Lees herinneringe

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Skep 'n herinnering

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lees gesprekke

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lees oop aksie-items

```bash
omi action-item list --json --open
```

### 5. Merk 'n aksie-item as afgehandel

```bash
omi action-item complete --json a1b2c3d4
```

## Plaaslike Desktop-API

Wanneer Omi Desktop sy plaaslike API beskikbaar stel, kan agente skermgeskiedenis,
opsommings, SQL en take op die toestel navraag doen sonder die wolk-ontwikkelaar-API:

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

Voltooi of verwyder take slegs wanneer die gebruiker dit duidelik vra:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skryf die skermskoot na
skyf en skryf steeds JSON na stdout vir skripte. Die skermskoot-ID kom gewoonlik
van `local search-screen` of SQL oor die `screenshots`-tabel. As Desktop
'n gestruktureerde mislukking soos `screenshot_pending`, `screenshot_file_missing`,
of `screenshot_chunk_corrupted` teruggee, behou JSON-modus die `reason`, `hint` en
`screenshot_id`-velde op stderr sodat agente 'n ouer ID kan herprobeer of die
presiese blokkering kan rapporteer. Valideer suksesvolle uitvoer met `file PATH`
voordat dit aan visuele hulpmiddele deurgegee word.

## Uitgewerkte voorbeeld: Python-agentlus

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

## Hantering van tempolimiete

Herinneringe: 120/uur. Gesprekke: 25/uur. Bondelskeppings: 15/uur.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Wenke

* Gebruik `--profile <name>` as jou agent verskeie Omi-rekeninge hanteer. Elke
  profiel het sy eie geloofsbrief en API-basis.
* Gebruik `--api-base http://localhost:8080` vir plaaslike agterkanttoetsing.
* Gebruik `OMI_LOCAL_API_URL` en `OMI_LOCAL_TOKEN` om profiel-plaaslike
  Desktop-API-instellings vir een lopie te oorheers.
* Gebruik `--verbose` vir ontfouting — dit skryf `METHOD path → status (Ns)` na stderr
  sonder om stdout te beïnvloed, dus bly JSON-modus geldig.
* Om inhoud na 'n gesprek te pyp, gebruik `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
