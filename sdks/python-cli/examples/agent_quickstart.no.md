# omi-cli for AI-agenter

> Praktisk veiledning for LLM-drevne systemer (Claude Code, Cursor, egne boter).

## Hvorfor CLI-en er agentvennlig

* **Stabil JSON-kontrakt.** `--json` sender et gyldig JSON-dokument til stdout og
  *kun* et JSON-dokument — ingen fremdriftsmeldinger, ingen innlastingssymboler. Feil
  sendes til stderr som `{"error": "...", "detail": "..."}`.
* **Stabile avslutningskoder.** `0` ok / `1` bruksfeil / `2` autentisering / `3` serverfeil /
  `4` hastighetsgrense nådd / `5` ikke funnet. Agenter kan forgrene logikk basert på disse uten
  å tolke feilmeldinger i naturlig språk.
* **Ingen interaktive meldinger i headless-kontekster.** Send `--yes` (eller `-y`) til destruktive
  handlinger; send `--api-key` eller sett miljøvariabelen `OMI_API_KEY` for å hoppe over
  interaktiv innlogging.
* **Tilgivende oppførsel ved nye forsøk.** Feil av typen `429` og `5xx` prøves automatisk på
  nytt med eksponensiell tilbakeholdenhet (backoff) før de rapporteres utad.

## Autentisering (engangs, av mennesket)

Brukeren henter en dev API-nøkkel fra Omi-nettapplikasjonen
(`https://app.omi.me` → Developer → API Keys) og enten:

```bash
omi auth login                          # interaktiv innliming; nøkkelen lagres ikke i shell-historikken
# eller
export OMI_API_KEY=omi_dev_...          # midlertidig, container-vennlig
```

## De fem tingene agenter gjør oftest

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

### 4. Les åpne handlingselementer

```bash
omi action-item list --json --open
```

### 5. Merk et handlingselement som fullført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop API

Når Omi Desktop eksponerer sitt lokale API, kan agenter spørre lokal skjermhistorikk,
sammendrag, SQL og oppgaver uten å bruke dev-API-et i skyen:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller for midlertidige økter:
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

Fullfør eller slett oppgaver kun når brukeren uttrykkelig ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Kommandoen `omi local screenshot SCREENSHOT_ID --output PATH` lagrer skjermbildet på disken
og skriver fortsatt ut JSON til stdout for skriptbruk. Skjermbilde-ID-en kommer vanligvis fra
`local search-screen` eller en SQL-spørring mot `screenshots`-tabellen. Hvis Desktop returnerer
en strukturert feil som `screenshot_pending`, `screenshot_file_missing` eller
`screenshot_chunk_corrupted`, bevarer JSON-modusen feltene `reason`, `hint` og `screenshot_id`
på stderr slik at agenter kan prøve en eldre ID eller rapportere den nøyaktige blokkeringen.
Valider vellykkede utdata med `file PATH` før de sendes videre til bildeanalyseverktøy (vision tools).

## Gjennomarbeidet eksempel: Python-agentløkke

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

## Håndtering av hastighetsgrenser (Rate limits)

Minner: 120/time. Samtaler: 25/time. Gruppeopprettelser: 15/time.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Bruk `--profile <name>` hvis agenten din administrerer flere Omi-kontoer. Hver
  profil har sine egne påloggingsdetaljer og API-base.
* Bruk `--api-base http://localhost:8080` for lokal backend-testing.
* Bruk `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` for å overstyre profilens lokale
  Desktop API-innstillinger for én enkelt kjøring.
* Bruk `--verbose` for feilsøking — den logger `METHOD path → status (Ns)` til stderr
  uten å påvirke stdout, slik at JSON-modusen forblir gyldig.
* For å videresende innhold inn i en samtale, bruk `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
