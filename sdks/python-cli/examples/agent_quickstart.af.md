# omi-cli vir AI-agente

> Praktiese gids vir LLM-gedrewe omgewings (Claude Code, Cursor, jou eie bots).

## Waarom die CLI agent-vriendelik is

* **Stabiele JSON-kontrak.** `--json` lewer 'n geldige JSON-dokument na stdout en
  *slegs* 'n JSON-dokument — geen vorderingsboodskappe, geen wag-animasies nie. Foute gaan na
  stderr as `{"error": "...", "detail": "..."}`.
* **Stabiele uitgangskodes.** `0` reg / `1` gebruiksfout / `2` verifikasiefout / `3` bedienerfout / `4` koers
  beperk / `5` nie gevind nie. Agente kan hierop vertak sonder om natuurlike-taal
  foute te ontleed.
* **Geen interaktiewe keuses in outonome kontekste nie.** Gee `--yes` (of `-y`) aan
  vernietigende opdragte; gee `--api-key` of stel `OMI_API_KEY` om
  interaktiewe aanmelding oor te slaan.
* **Vergewensgesinde herprobeergedrag.** `429` en `5xx` word outomaties herprobeer met
  terugvalvertraging (backoff) voordat 'n fout na vore gebring word.

## Verifikasie (eenmalig, deur die mens)

Die gebruiker verkry 'n ontwikkelaar-API-sleutel vanaf die Omi-webtoepassing
(`https://app.omi.me` → Developer → API Keys) en doen een van die volgende:

```bash
omi auth login                          # interaktiewe plak; sleutel nie in terminaalgeskiedenis nie
# of
export OMI_API_KEY=omi_dev_...          # tydelik, houer-vriendelik (container-friendly)
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

### 5. Merk 'n aksie-item as voltooi

```bash
omi action-item complete --json a1b2c3d4
```

## Plaaslike Werkskerm-API (Desktop API)

Wanneer Omi Desktop sy plaaslike API beskikbaar stel, kan agente toestel-skermgeskiedenis,
opsommings, SQL en take navra sonder om die wolk-ontwikkelaar-API te gebruik:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# of, vir tydelike sessies:
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

Voltooi of verwyder take slegs wanneer die gebruiker uitdruklik so vra:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skryf die skermkiekie na
skyf en druk steeds JSON na stdout vir skrifte. Die skermkiekie-ID kom gewoonlik
vanaf `local search-screen` of SQL oor die `screenshots`-tabel. Indien Desktop
'n gestruktureerde fout lewer soos `screenshot_pending`, `screenshot_file_missing`,
of `screenshot_chunk_corrupted`, behou JSON-modus die velde `reason`, `hint`, en
`screenshot_id` op stderr sodat agente 'n ouer ID kan herprobeer of die presiese
hindernis kan rapporteer. Valideer suksesvolle afvoer met `file PATH` voordat dit
aan visie-gereedskap oorgedra word.

## Praktiese voorbeeld: Python-agentsiklus

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Roep die omi CLI in JSON-modus aan, en veroorsaak 'n fout op nie-suksesvolle uitgangskodes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Die CLI druk gestruktureerde foute na stderr in JSON-modus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi het afgesluit met {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lees alle oop aksie-items en merk enige items ouer as 30 dae as voltooi.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Hantering van versoeklimiete (Rate Limits)

Herinneringe: 120/uur. Gesprekke: 25/uur. Bondelskeppings: 15/uur.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # koers beperk (rate limited)
    err = json.loads(result.stderr)
    # err["detail"] lyk soos: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Wenke

* Gebruik `--profile <naam>` as jou agent verskeie Omi-rekeninge hanteer. Elke
  profiel het sy eie geloofsbriewe en API-basis.
* Gebruik `--api-base http://localhost:8080` vir plaaslike agterkant-toetsing.
* Gebruik `OMI_LOCAL_API_URL` en `OMI_LOCAL_TOKEN` om profiel-plaaslike
  Desktop API-instellings vir een lopie te ignoreer.
* Gebruik `--verbose` vir ontfouting — dit teken `METHOD path → status (Ns)` na stderr aan
  sonder om stdout te beïnvloed, sodat JSON-modus geldig bly.
* Om inhoud na 'n gesprek te stroom, gebruik `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
