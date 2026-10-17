# omi-cli för agenter

> Praktisk guide för LLM-styrda harnesses (Claude Code, Cursor, egna bottar).

## Varför CLI:t är agentvänligt

* **Stabilt JSON-kontrakt.** `--json` skriver ett giltigt JSON-dokument till stdout och *bara* JSON — inga progressmeddelanden eller spinnare. Fel går till stderr som `{"error": "...", "detail": "..."}`.
* **Stabila exitkoder.** `0` ok / `1` användning / `2` auth / `3` server / `4` rate limited / `5` hittades inte. Agenter kan grensla på dessa utan att tolka fel i naturligt språk.
* **Inga interaktiva prompts i headless-kontexter.** Skicka `--yes` (eller `-y`) till destruktiva kommandon; skicka `--api-key` eller sätt `OMI_API_KEY` för att hoppa över interaktiv inloggning.
* **Förlåtande omförsök.** `429` och `5xx` återförsöks med backoff innan de bubblar upp.

## Autentisering (engångs, av människan)

Användaren hämtar en dev API-nyckel från Omi-webbappen
(`https://app.omi.me` → Developer → API Keys) och antingen:

```bash
omi auth login                          # interaktiv inklistring; nyckeln inte i shell-historik
# # eller
export OMI_API_KEY=omi_dev_...          # efemär, container-vänlig
```

## De fem saker agenter gör mest

### 1. Läs memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Skapa en memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Läs conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Läs öppna action items

```bash
omi action-item list --json --open
```

### 5. Markera action item som klar

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal Desktop-API

När Omi Desktop exponerar sin lokala API kan agenter fråga on-device
screen history, recaps, SQL och tasks utan molnets dev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # eller, för kortlivade sessioner:
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

Slutför eller ta bort tasks bara när användaren uttryckligen ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skriver skärmdumpen till
disk och skriver ändå JSON till stdout för skript. Screenshot-ID kommer oftast
från `local search-screen` eller SQL över tabellen `screenshots`. Om Desktop
returnerar ett strukturerat fel som `screenshot_pending`, `screenshot_file_missing`
eller `screenshot_chunk_corrupted` bevarar JSON-läget `reason`, `hint` och
`screenshot_id` på stderr så agenter kan prova ett äldre ID eller rapportera
exakt blocker. Validera lyckade outputs med `file PATH` innan de skickas till
visionsverktyg.

## Genomarbetat exempel: Python agent-loop

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

# Läs alla öppna action items och markera allt äldre än 30 dagar som klart.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Hantera rate limits

Memories: 120/h. Conversations: 25/h. Batch-skapanden: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] ser ut som: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Använd `--profile <name>` om agenten jonglerar flera Omi-konton. Varje
  profil har egna credentials och API-bas.
* Använd `--api-base http://localhost:8080` för lokal backend-testning.
* Använd `OMI_LOCAL_API_URL` och `OMI_LOCAL_TOKEN` för att åsidosätta
  profillokala Desktop-API-inställningar för en körning.
* Använd `--verbose` för felsökning — loggar `METHOD path → status (Ns)` till
  stderr utan att påverka stdout, så JSON-läget förblir giltigt.
* För att pipa innehåll till en conversation, använd `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
