# omi-cli til agenter

> Praktisk guide til LLM-drevne harnesses (Claude Code, Cursor, dine egne bots).

## Hvorfor CLI'en er agentvenlig

* **Stabil JSON-kontrakt.** `--json` udskriver et gyldigt JSON-dokument til stdout og
  *kun* et JSON-dokument — ingen statusbeskeder, ingen spinners. Fejl går til
  stderr som `{"error": "...", "detail": "..."}`.
* **Stabile exit-koder.** `0` ok / `1` brug / `2` auth / `3` server / `4`
  rate limited / `5` ikke fundet. Agenter kan grene på disse uden at fortolke
  fejl på naturligt sprog.
* **Ingen interaktive prompts i headless-kontekster.** Send `--yes` (eller `-y`) til
  destruktive kommandoer; send `--api-key` eller sæt `OMI_API_KEY` for at springe
  interaktiv login over.
* **Tilgivende opførsel ved gentagelse.** `429` og `5xx` prøves igen med backoff
  før de vises.

## Auth (en gang, af mennesket)

Brugeren henter en dev API-nøgle fra Omi-webappen
(`https://app.omi.me` → Developer → API Keys) og enten:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## De fem ting agenter gør oftest

### 1. Læs memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Opret en memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Læs samtaler

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Læs åbne action items

```bash
omi action-item list --json --open
```

### 5. Markér en action item som færdig

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal Desktop API

Når Omi Desktop eksponerer sit lokale API, kan agente spørge om enhedens
skærmhistorik, recap, SQL og opgaver uden at bruge skyens dev API:

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

Gennemfør eller slet opgaver kun når brugeren tydeligt beder om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skriver skærmbilledet til
disken og udskriver stadig JSON til stdout for scripts. Skærmbilledets ID kommer
normalt fra `local search-screen` eller SQL over `screenshots`-tabellen. Hvis
Desktop returnerer en struktureret fejl som `screenshot_pending`,
`screenshot_file_missing` eller `screenshot_chunk_corrupted`, bevarer JSON-tilstand
felterne `reason`, `hint` og `screenshot_id` på stderr, så agenter kan prøve et
ældre ID eller rapportere den præcise blokering. Valider vellykkede output med
`file PATH` før du sender dem til vision-værktøjer.

## Gennemarbejdet eksempel: Python agent-loop

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

## Håndtering af rate limits

Memories: 120/time. Samtaler: 25/time. Batch-oprettelser: 15/time.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Brug `--profile <navn>` hvis din agent håndterer flere Omi-konti. Hver
  profil har egne credentials og API base.
* Brug `--api-base http://localhost:8080` til lokal backend-testning.
* Brug `OMI_LOCAL_API_URL` og `OMI_LOCAL_TOKEN` for at overskrive profil-lokale
  Desktop API-indstillinger for ét kørsel.
* Brug `--verbose` til fejlfinding — logger `METHOD path → status (Ns)` til stderr
  uden at påvirke stdout, så JSON-tilstand forbliver gyldig.
* For at pipe indhold ind i en samtale, brug `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
