# omi-cli for agenter

> Praktisk guide for LLM-drevne harnesser (Claude Code, Cursor, dine egne boter).

## Hvorfor CLI-en er agentvennlig

* **Stabil JSON-kontrakt.** `--json` skriver ut et gyldig JSON-dokument til stdout og
  *kun* et JSON-dokument — ingen fremdriftsmeldinger, ingen spinners. Feil går til
  stderr som `{"error": "...", "detail": "..."}`.
* **Stabile exit-koder.** `0` ok / `1` bruk / `2` auth / `3` server / `4`
  rate limited / `5` ikke funnet. Agenter kan grene på disse uten å tolke
  feil på naturlig språk.
* **Ingen interaktive forespørsler i headless-miljøer.** Send `--yes` (eller `-y`) til
  destruktive kommandoer; send `--api-key` eller sett `OMI_API_KEY` for å hoppe over
  interaktiv pålogging.
* **Tilgivende atferd ved ny forsøk.** `429` og `5xx` prøves på nytt med backoff
  før de vises.

## Auth (en gang, av mennesket)

Brukeren henter en dev API-nøkkel fra Omi-nettappen
(`https://app.omi.me` → Developer → API Keys) og enten:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## De fem tingene agenter gjør oftest

### 1. Les minner

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Lag et minne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Les samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Les åpne action items

```bash
omi action-item list --json --open
```

### 5. Merk en action item som fullført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal Desktop API

Når Omi Desktop eksponerer sitt lokale API, kan agenter spørre om enhetens
skjerminnhold, sammendrag, SQL og oppgaver uten å bruke skyens dev API:

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

Fullfør eller slett oppgaver bare når brukeren tydelig ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skjermbildet til disk og
skriver fortsatt JSON til stdout for skript. Skjermbilde-ID-en kommer vanligvis
fra `local search-screen` eller SQL over `screenshots`-tabellen. Hvis Desktop
returnerer en strukturert feil som `screenshot_pending`, `screenshot_file_missing`
eller `screenshot_chunk_corrupted`, bevarer JSON-modus feltene `reason`, `hint`
og `screenshot_id` på stderr slik at agenter kan prøve en eldre ID eller rapportere
den nøyaktige hindringen. Valider vellykkede utdata med `file PATH` før du sender
dem til visjonsverktøy.

## Gjennomarbeidet eksempel: Python agent-løkke

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

## Håndtering av rate limits

Minner: 120/time. Samtaler: 25/time. Satsopprettelser: 15/time.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Bruk `--profile <navn>` hvis agenten din håndterer flere Omi-kontoer. Hver
  profil har egne legitimasjoner og API base.
* Bruk `--api-base http://localhost:8080` for lokal backend-testing.
* Bruk `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` for å overstyre profil-lokale
  Desktop API-innstillinger for én kjøring.
* Bruk `--verbose` for feilsøking — logger `METHOD path → status (Ns)` til stderr
  uten å påvirke stdout, slik at JSON-modus forblir gyldig.
* For å pipe innhold inn i en samtale, bruk `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
