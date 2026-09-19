# omi-cli for agenter

> Praktisk veiledning for LLM-drevne miljøer (Claude Code, Cursor, dine egne roboter).

## Hvorfor CLI-en er agentvennlig

* **Stabil JSON-kontrakt.** `--json` sender et gyldig JSON-dokument til stdout og *utelukkende* et JSON-dokument — ingen fremdriftsmeldinger eller lasteindikatorer. Feil sendes til stderr som `{"error": "...", "detail": "..."}`.
* **Stabile avslutningskoder.** `0` ok / `1` bruksfeil / `2` autentisering / `3` server / `4` hastighetsbegrenset / `5` ikke funnet. Agenter kan forgrene seg på disse uten å måtte tolke feilmeldinger på naturlig språk.
* **Ingen interaktive ledetekster i hodeløse kontekster.** Send med `--yes` (eller `-y`) til destruktive kommandoer; send `--api-key` eller angi `OMI_API_KEY` for å hoppe over interaktiv pålogging.
* **Tilgivende oppførsel ved nye forsøk.** `429` og `5xx` prøves på nytt med eksponensiell tilbakeholdenhet før de vises.

## Autentisering (én gang, av mennesket)

Brukeren henter en API-nøkkel for utviklere fra Omi-nettappen (`https://app.omi.me` → Developer → API Keys) og velger ett av følgende:

```bash
omi auth login                          # interaktiv innliming; nøkkelen lagres ikke i skallhistorikken
# eller
export OMI_API_KEY=omi_dev_...          # midlertidig, beholder-vennlig
```

## De fem tingene agenter gjør oftest

### 1. Lese minner

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Opprette et minne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lese samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lese åpne handlingselementer

```bash
omi action-item list --json --open
```

### 5. Merke et handlingselement som fullført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop API

Når Omi Desktop eksponerer sitt lokale API, kan agenter spørre etter skjermhistorikk på enheten, sammendrag, SQL og oppgaver uten å bruke dev-API-et i skyen:

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

Fullfør eller slett bare oppgaver når brukeren uttrykkelig ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` lagrer skjermbildet til disk og skriver fortsatt JSON til stdout for skript. Skjermbilde-ID kommer vanligvis fra `local search-screen` eller SQL over tabellen `screenshots`. Hvis Desktop returnerer en strukturert feil som `screenshot_pending`, `screenshot_file_missing` eller `screenshot_chunk_corrupted`, bevarer JSON-modus feltene `reason`, `hint` og `screenshot_id` på stderr slik at agenter kan prøve en eldre ID på nytt eller rapportere den nøyaktige hindringen. Bekreft vellykkede filer med `file PATH` før de sendes til synsverktøy.

## Praktisk eksempel: Python-agentsløyfe

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kjører omi CLI i JSON-modus og reiser et unntak ved mislykkede avslutningskoder."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI-en skriver strukturerte feil til stderr i JSON-modus:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi avsluttet med kode {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leser alle åpne handlingselementer og merker de som er eldre enn 30 dager som fullført.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Håndtering av hastighetsbegrensninger

Minner: 120/time. Samtaler: 25/time. Gruppeopprettelse: 15/time.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hastighetsbegrenset
    err = json.loads(result.stderr)
    # err["detail"] ser slik ut: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Bruk `--profile <navn>` hvis agenten din håndterer flere Omi-kontoer. Hver profil har sine egne legitimasjoner og API-base.
* Bruk `--api-base http://localhost:8080` for lokal backend-testing.
* Bruk `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` for å overstyre profil-lokale Desktop API-innstillinger for én kjøring.
* Bruk `--verbose` for feilsøking — det logger `METHOD path → status (Ns)` til stderr uten å påvirke stdout, slik at JSON-modusen forblir gyldig.
* For å sende innhold inn i en samtale via rør (pipe), bruk `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
