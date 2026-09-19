# omi-cli voor agents

> Praktische gids voor LLM-gestuurde harnesses (Claude Code, Cursor, je eigen bots).

## Waarom de CLI agent-vriendelijk is

* **Stabiel JSON-contract.** `--json` stuurt een geldig JSON-document naar stdout en
  *uitsluitend* een JSON-document — geen voortgangsberichten, geen spinners. Fouten gaan naar
  stderr als `{"error": "...", "detail": "..."}`.
* **Stabiele afsluitcodes.** `0` ok / `1` gebruiksfout / `2` authenticatie / `3` serverfout /
  `4` snelheidslimiet bereikt / `5` niet gevonden. Agents kunnen op basis van deze codes vertakken
  zonder foutmeldingen in natuurlijke taal te hoeven ontleden.
* **Geen interactieve prompts in headless-omgevingen.** Geef `--yes` (of `-y`) mee aan
  destructieve opdrachten; geef `--api-key` mee of stel `OMI_API_KEY` in om interactief inloggen over te slaan.
* **Vergevingsgezind herhaalgedrag.** Fouten van het type `429` en `5xx` worden automatisch
  opnieuw geprobeerd met backoff voordat ze naar voren worden gebracht.

## Authenticatie (eenmalig, door de mens)

De gebruiker haalt een ontwikkelaars-API-sleutel op via de Omi-webapp
(`https://app.omi.me` → Developer → API Keys) en kiest een van de volgende opties:

```bash
omi auth login                          # interactief plakken; sleutel komt niet in shell-geschiedenis
# of
export OMI_API_KEY=omi_dev_...          # vluchtig, container-vriendelijk
```

## De vijf acties die agents het meest uitvoeren

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

## Lokale Desktop-API

Wanneer Omi Desktop de lokale API beschikbaar stelt, kunnen agents schermgeschiedenis,
samenvattingen, SQL en taken op het apparaat bevragen zonder de cloud dev-API te gebruiken:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# of voor tijdelijke sessies:
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

Voltooi of verwijder taken alleen wanneer de gebruiker hier duidelijk om vraagt:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schrijft de schermafbeelding naar schijf
en blijft JSON naar stdout sturen voor scripts. De screenshot-ID is meestal afkomstig van
`local search-screen` of een SQL-query op de tabel `screenshots`. Als Desktop een
gestructureerde fout retourneert zoals `screenshot_pending`, `screenshot_file_missing` of
`screenshot_chunk_corrupted`, behoudt de JSON-modus de velden `reason`, `hint` en `screenshot_id`
op stderr, zodat agents het opnieuw kunnen proberen met een eerdere ID of de exacte blokkade kunnen melden.
Valideer geslaagde uitvoer met `file PATH` alvorens deze aan visiehulpmiddelen door te geven.

## Praktijkvoorbeeld: Python-agentlus

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

## Omgaan met snelheidslimieten (rate limits)

Herinneringen: 120/uur. Gesprekken: 25/uur. Batch-aanmaak: 15/uur.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gebruik `--profile <naam>` als je agent meerdere Omi-accounts beheert. Elk profiel
  heeft zijn eigen inloggegevens en API-basis-URL.
* Gebruik `--api-base http://localhost:8080` voor lokale backendtests.
* Gebruik `OMI_LOCAL_API_URL` en `OMI_LOCAL_TOKEN` om de lokale Desktop-API-instellingen
  van het profiel voor één run te overschrijven.
* Gebruik `--verbose` voor foutopsporing — dit logt `METHOD path → status (Ns)` naar stderr
  zonder stdout te beïnvloeden, waardoor de JSON-modus intact blijft.
* Om inhoud via een pipe naar een gesprek te sturen, gebruik je `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
