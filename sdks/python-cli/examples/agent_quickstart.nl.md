# omi-cli voor agents

> Praktische gids voor LLM-gedreven harnesses (Claude Code, Cursor, je eigen bots).

## Waarom de CLI agentvriendelijk is

* **Stabiel JSON-contract.** `--json` geeft een geldig JSON-document naar stdout en
  *alleen* een JSON-document — geen voortgangsberichten, geen spinners. Fouten gaan naar
  stderr als `{"error": "...", "detail": "..."}`.
* **Stabiele exit-codes.** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` niet gevonden. Agents kunnen hierop branchen zonder
  natuurlijketaalfouten te parsen.
* **Geen interactieve prompts in headless-contexten.** Geef `--yes` (of `-y`) aan
  destructieve commando's; geef `--api-key` of zet `OMI_API_KEY` om interactieve
  login over te slaan.
* **Vergevingsgezind gedrag bij retries.** `429` en `5xx` worden met backoff opnieuw
  geprobeerd voordat ze getoond worden.

## Auth (eenmalig, door de mens)

De gebruiker haalt een dev API-sleutel op in de Omi-webapp
(`https://app.omi.me` → Developer → API Keys) en doet een van beide:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
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

### 3. Conversaties lezen

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Openstaande actiepunten lezen

```bash
omi action-item list --json --open
```

### 5. Een actiepunt afronden

```bash
omi action-item complete --json a1b2c3d4
```

## Lokale Desktop API

Wanneer Omi Desktop zijn lokale API ontsluit, kunnen agents apparaat-schermgeschiedenis,
recaps, SQL en taken raadplegen zonder de cloud dev API te gebruiken:

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

Rond taken alleen af of verwijder ze wanneer de gebruiker dat duidelijk vraagt:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` schrijft de schermafbeelding naar
schijf en blijft JSON naar stdout printen voor scripts. De screenshot-ID komt meestal
uit `local search-screen` of SQL over de `screenshots`-tabel. Als Desktop een
gestructureerde fout teruggeeft zoals `screenshot_pending`, `screenshot_file_missing`
of `screenshot_chunk_corrupted`, bewaart JSON-modus de velden `reason`, `hint` en
`screenshot_id` op stderr zodat agents een oudere ID kunnen herproberen of het
exacte blokkeringspunt kunnen melden. Valideer geslaagde uitvoer met `file PATH`
voordat je ze doorgeeft aan vision-tools.

## Uitgewerkt voorbeeld: Python agent loop

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

## Omgaan met rate limits

Herinneringen: 120/uur. Conversaties: 25/uur. Batch-creates: 15/uur.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Gebruik `--profile <naam>` als je agent meerdere Omi-accounts beheert. Elk
  profiel heeft eigen credentials en API base.
* Gebruik `--api-base http://localhost:8080` voor lokale backend-tests.
* Gebruik `OMI_LOCAL_API_URL` en `OMI_LOCAL_TOKEN` om profiel-lokale
  Desktop API-instellingen voor één run te overschrijven.
* Gebruik `--verbose` voor debuggen — logt `METHOD path → status (Ns)` naar stderr
  zonder stdout te beïnvloeden, zodat JSON-modus geldig blijft.
* Om content in een conversatie te pipen, gebruik `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
