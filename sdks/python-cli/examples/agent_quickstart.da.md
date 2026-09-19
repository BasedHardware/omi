# omi-cli for agenter

> Praktisk vejledning til LLM-drevne værktøjer (Claude Code, Cursor, dine egne robotter).

## Hvorfor CLI'et er agentvenligt

* **Stabil JSON-kontrakt.** `--json` udsender et gyldigt JSON-dokument til stdout og
  *kun* et JSON-dokument — ingen statusmeddelelser eller animationer. Fejl sendes til
  stderr som `{"error": "...", "detail": "..."}`.
* **Stabile afslutningskoder.** `0` ok / `1` brugsfejl / `2` autentificering / `3` serverfejl / `4` hastighedsbegrænset / `5` ikke fundet. Agenter kan forgrene på disse uden at fortolke fejlmeddelelser på naturligt sprog.
* **Ingen interaktive meddelelser i headless-kontekster.** Send `--yes` (eller `-y`) til
  destruktive kommandoer; send `--api-key` eller indstil `OMI_API_KEY` for at springe interaktivt login over.
* **Tilgivende adfærd ved genforsøg.** Koderne `429` og `5xx` genforsøges med tidsmæssig tilbageholdelse,
  før fejlen vises.

## Autentificering (engangs, af mennesket)

Brugeren henter en udvikler-API-nøgle fra Omi-webappen
(`https://app.omi.me` → Developer → API Keys) og vælger enten:

```bash
omi auth login                          # interaktiv indsættelse; nøglen gemmes ikke i shell-historikken
# eller
export OMI_API_KEY=omi_dev_...          # midlertidig, velegnet til containere
```

## De fem ting, agenter gør mest

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

### 5. Markér et handlingspunkt som udført

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Skrivebords-API (Desktop API)

Når Omi Desktop stiller sit lokale API til rådighed, kan agenter forespørge skærmhistorik på enheden,
opsummeringer, SQL og opgaver uden brug af cloud-API'et:

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

Afslut eller slet kun opgaver, når brugeren udtrykkeligt beder om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Kommandoen `omi local screenshot SCREENSHOT_ID --output PATH` skriver skærmbilledet til
disken og udskriver stadig JSON til stdout for scripts. Skærmbillede-id'et stammer normalt
fra `local search-screen` eller en SQL-forespørgsel på tabellen `screenshots`. Hvis Desktop
returnerer en struktureret fejl som `screenshot_pending`, `screenshot_file_missing`
eller `screenshot_chunk_corrupted`, bevarer JSON-tilstand felterne `reason`, `hint` og
`screenshot_id` på stderr, så agenter kan prøve et ældre id igen eller rapportere
den præcise blokering. Valider vellykkede resultater med `file PATH`, før de sendes videre
til billedbehandlingsværktøjer.

## Gennemgået eksempel: Python-agentløkke

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Kør omi CLI i JSON-tilstand, og udløs undtagelse ved fejlkoder."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI udskriver strukturerede fejl til stderr i JSON-tilstand:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Læs alle åbne handlingspunkter og markér alt ældre end 30 dage som udført.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Håndtering af hastighedsbegrænsninger (rate limits)

Minder: 120/time. Samtaler: 25/time. Batch-oprettelser: 15/time.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hastighedsbegrænset
    err = json.loads(result.stderr)
    # err["detail"] ser sådan ud: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Brug `--profile <navn>`, hvis din agent håndterer flere Omi-konti. Hver
  profil har sine egne legitimationsoplysninger og API-adresse.
* Brug `--api-base http://localhost:8080` til lokal afprøvning mod backend.
* Brug `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` til at tilsidesætte profilens lokale
  Desktop API-indstillinger for en enkelt kørsel.
* Brug `--verbose` til fejlfinding — det logger `METHOD path → status (Ns)` til stderr
  uden at påvirke stdout, så JSON-tilstanden forbliver gyldig.
* Hvis du vil sende indhold ind i en samtale via pipe, skal du bruge `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
