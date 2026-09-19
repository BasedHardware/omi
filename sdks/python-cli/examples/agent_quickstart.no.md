# omi-cli for agenter

> Praktisk veiledning for LLM-drevne verktøy (Claude Code, Cursor, egne boter).

## Hvorfor CLI-et er agentvennlig

* **Stabil JSON-kontrakt.** `--json` sender et gyldig JSON-dokument til stdout og
  *bare* et JSON-dokument — ingen fremdriftsmeldinger eller spinnere. Feil sendes til
  stderr som `{"error": "...", "detail": "..."}`.
* **Stabile avslutningskoder.** `0` ok / `1` bruksfeil / `2` autentisering / `3` tjenerfeil / `4` hastighetsbegrenset / `5` ikke funnet. Agenter kan forgrene logikk basert på disse uten å tolke feilmeldinger på naturlig språk.
* **Ingen interaktive ledetekster i hodeløse kontekster.** Bruk `--yes` (eller `-y`) ved
  destruktive handlinger; bruk `--api-key` eller sett `OMI_API_KEY` for å hoppe over
  interaktiv innlogging.
* **Tilgivende prøve-igjen-atferd.** `429` og `5xx` prøves på nytt med eksponensiell tilbakeholdelse
  før de rapporteres.

## Autentisering (én gang, av mennesket)

Brukeren henter en utvikler-API-nøkkel fra Omi-nettappen
(`https://app.omi.me` → Developer → API Keys) og enten:

```bash
omi auth login                          # interaktiv innliming; nøkkelen lagres ikke i shell-historikken
# eller
export OMI_API_KEY=omi_dev_...          # flyktig, beholder-vennlig
```

## De fem tingene agenter gjør mest

### 1. Les minner

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Opprett et minne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Les samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Les åpne gjøremål

```bash
omi action-item list --json --open
```

### 5. Merk et gjøremål som fullført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop-API

Når Omi Desktop eksponerer sitt lokale API, kan agenter spørre skjermhistorikk på enheten,
oppsummeringer, SQL og oppgaver uten å bruke sky-API-et:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller, for flyktige økter:
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

Fullfør eller slett bare oppgaver når brukeren uttrykkelig ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skriver skjermbildet til
disk og returnerer fortsatt JSON til stdout for skript. Skjermbilde-ID-en kommer
vanligvis fra `local search-screen` eller SQL over `screenshots`-tabellen. Hvis Desktop
returnerer en strukturert feil som `screenshot_pending`, `screenshot_file_missing`,
eller `screenshot_chunk_corrupted`, beholder JSON-modus feltene `reason`, `hint` og
`screenshot_id` på stderr slik at agenter kan prøve en eldre ID på nytt eller rapportere
den nøyaktige blokkeringen. Valider vellykkede resultater med `file PATH` før de sendes
videre til synsverktøy.

## Gjennomgått eksempel: Python-agentløkke

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kjør omi CLI i JSON-modus, og utløs unntak ved feilkoder."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI-et skriver strukturerte feil til stderr i JSON-modus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Les alle åpne gjøremål og merk alt eldre enn 30 dager som fullført.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Håndtering av hastighetsbegrensninger (rate limits)

Minner: 120/t. Samtaler: 25/t. Gruppeopprettelser: 15/t.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hastighetsbegrenset
    err = json.loads(result.stderr)
    # err["detail"] ser slik ut: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Bruk `--profile <navn>` hvis agenten håndterer flere Omi-kontoer. Hver
  profil har sine egne legitimasjoner og API-adresse.
* Bruk `--api-base http://localhost:8080` for testing mot lokal backend.
* Bruk `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` for å overstyre profilens lokale
  Desktop API-innstillinger for én enkelt kjøring.
* Bruk `--verbose` for feilsøking — den logger `METHOD path → status (Ns)` til stderr
  uten å påvirke stdout, slik at JSON-modus forblir gyldig.
* For å sende innhold inn i en samtale via rør, bruk `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
