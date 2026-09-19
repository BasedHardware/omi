# omi-cli til AI-agenter

> Praktisk vejledning til LLM-drevne systemer (Claude Code, Cursor, egne bots).

## Hvorfor CLI'en er agentvenlig

* **Stabil JSON-kontrakt.** `--json` udsender et gyldigt JSON-dokument til stdout og
  *udelukkende* et JSON-dokument — ingen statusmeddelelser, ingen indlæsningsikoner. Fejl
  sendes til stderr som `{"error": "...", "detail": "..."}`.
* **Stabile slutkoder.** `0` ok / `1` brug / `2` godkendelse / `3` server / `4` hastighedsbegrænset /
  `5` ikke fundet. Agenter kan forgrene sig baseret på disse uden at fortolke tekstfejl.
* **Ingen interaktive meddelelser i headless-kontekster.** Send `--yes` (eller `-y`) til
  destruktive handlinger; send `--api-key` eller angiv `OMI_API_KEY` for at springe interaktivt
  login over.
* **Tilgivende genforsøgsadfærd.** `429` og `5xx` genforsøges automatisk med backoff, før de
  rapporteres udad.

## Autentificering (engangs, af mennesket)

Brugeren henter en dev API-nøgle fra Omi-webapplikationen
(`https://app.omi.me` → Developer → API Keys) og enten:

```bash
omi auth login                          # interaktiv indsættelse; nøglen gemmes ikke i shell-historikken
# eller
export OMI_API_KEY=omi_dev_...          # midlertidig, container-venlig
```

## De fem ting agenter gør oftest

### 1. Læs minder

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Opret et minde

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Læs samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Læs åbne handlingspunkter

```bash
omi action-item list --json --open
```

### 5. Marker et handlingspunkt som udført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop API

Når Omi Desktop eksponerer sit lokale API, kan agenter forespørge lokal skærmhistorik,
resuméer, SQL og opgaver uden at anvende cloud dev-API'et:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller til midlertidige sessioner:
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

Fuldfør eller slet kun opgaver, når brugeren udtrykkeligt anmoder om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` gemmer skærmbilledet på disken
og udskriver fortsat JSON til stdout til brug i scripts. Skærmbilledets ID kommer normalt
fra `local search-screen` eller en SQL-forespørgsel på `screenshots`-tabellen. Hvis Desktop
returnerer en struktureret fejl som `screenshot_pending`, `screenshot_file_missing`
eller `screenshot_chunk_corrupted`, bevarer JSON-tilstanden felterne `reason`, `hint`
og `screenshot_id` på stderr, så agenter kan prøve et ældre ID eller rapportere den præcise blokering.
Valider succesfulde outputs med `file PATH`, før de sendes videre til vision-værktøjer.

## Gennemarbejdet eksempel: Python-agentløkke

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

## Håndtering af hastighedsgrænser (rate limits)

Minder: 120/time. Samtaler: 25/time. Batch-oprettelser: 15/time.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Brug `--profile <name>`, hvis din agent administrerer flere Omi-konti. Hver
  profil har sine egne legitimationsoplysninger og API-base.
* Brug `--api-base http://localhost:8080` til lokal backend-test.
* Brug `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` til at tilsidesætte de profil-lokale
  Desktop API-indstillinger for en enkelt kørsel.
* Brug `--verbose` til debugging — logger `METHOD path → status (Ns)` til stderr
  uden at påvirke stdout, så JSON-tilstanden forbliver gyldig.
* For at videresende indhold til en samtale, brug `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
