# omi-cli voor agents

> Praktische gids voor LLM-gestuurde harnesses (Claude Code, Cursor, je eigen bots).

## Waarom de CLI agent-vriendelijk is

* **Stabiel JSON-contract.** `--json` stuurt een geldig JSON-document naar stdout en *uitsluitend* een JSON-document — geen voortgangsberichten, geen laadspinners. Fouten gaan naar stderr als `{"error": "...", "detail": "..."}`.
* **Stabiele exit-codes.** `0` geslaagd / `1` gebruiksfout / `2` authenticatiefout / `3` serverfout / `4` rate limit bereikt / `5` niet gevonden. Agents kunnen op deze codes vertakken zonder foutberichten in natuurlijke taal te moeten parsen.
* **Geen interactieve prompts in headless contexten.** Geef `--yes` (of `-y`) mee voor destructieve commando's; geef `--api-key` mee of stel de omgevingsvariabele `OMI_API_KEY` in om interactief inloggen over te slaan.
* **Vergevingsgezind retry-gedrag.** `429`- en `5xx`-fouten worden automatisch opnieuw geprobeerd met backoff voordat ze naar boven komen.

## Authenticatie (eenmalig, door de mens)

De gebruiker haalt een developer API-sleutel op uit de Omi-webapp (`https://app.omi.me` → Developer → API Keys) en doet een van de volgende dingen:

```bash
omi auth login                          # interactief plakken; sleutel blijft niet in de shell-geschiedenis staan
# of
export OMI_API_KEY=omi_dev_...          # tijdelijk, geschikt voor containers
```

## De vijf dingen die agents het vaakst doen

### 1. Herinneringen lezen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Een herinnering aanmaken

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Gesprekken lezen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Openstaande actiepunten lezen

```bash
omi action-item list --json --open
```

### 5. Een actiepunt als voltooid markeren

```bash
omi action-item complete --json a1b2c3d4
```

## Lokale Desktop API

Wanneer Omi Desktop zijn lokale API openstelt, kunnen agents schermgeschiedenis, overzichten, SQL en taken op het apparaat bevragen zonder de cloud dev-API te gebruiken:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# of, voor tijdelijke sessies:
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

Voltooi of verwijder taken alleen als de gebruiker hier expliciet om vraagt:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schrijft het screenshot naar schijf en print nog steeds JSON naar stdout voor scripts. Het screenshot-ID is meestal afkomstig van `local search-screen` of een SQL-query over de `screenshots`-tabel. Als Desktop een gestructureerde fout retourneert, zoals `screenshot_pending`, `screenshot_file_missing` of `screenshot_chunk_corrupted`, behoudt de JSON-modus de velden `reason`, `hint` en `screenshot_id` op stderr, zodat agents opnieuw kunnen proberen met een ouder ID of de exacte blokkade kunnen rapporteren. Valideer succesvolle uitvoer met `file PATH` voordat je deze doorgeeft aan vision tools.

## Uitgewerkt voorbeeld: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Roept de omi CLI aan in JSON-modus en genereert een exceptie bij niet-succesvolle exit-codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # De CLI print gestructureerde fouten naar stderr in JSON-modus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lees alle openstaande actiepunten en markeer alles ouder dan 30 dagen als voltooid.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Omgaan met rate limits

Herinneringen: 120/uur. Gesprekken: 25/uur. Batch-creaties: 15/uur.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limit bereikt
    err = json.loads(result.stderr)
    # err["detail"] ziet er als volgt uit: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gebruik `--profile <name>` als je agent meerdere Omi-accounts beheert. Elk profiel heeft zijn eigen inloggegevens en API-basis.
* Gebruik `--api-base http://localhost:8080` voor lokale backend-tests.
* Gebruik `OMI_LOCAL_API_URL` en `OMI_LOCAL_TOKEN` om profiellokale Desktop API-instellingen voor één run te overschrijven.
* Gebruik `--verbose` voor debugging — dit logt `METHOD path → status (Ns)` naar stderr zonder stdout te beïnvloeden, zodat de JSON-modus geldig blijft.
* Om inhoud via een pipe naar een gesprek te sturen, gebruik `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
