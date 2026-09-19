# omi-cli för agenter

> Praktisk guide för LLM-drivna miljöer (Claude Code, Cursor, dina egna bottar).

## Varför detta CLI är agentvänligt

* **Stabilt JSON-kontrakt.** `--json` matar ut ett giltigt JSON-dokument till stdout och
  *endast* ett JSON-dokument — inga förloppsmeddelanden, inga spinners. Fel skickas till
  stderr som `{"error": "...", "detail": "..."}`.
* **Stabila slutkoder.** `0` ok / `1` användningsfel / `2` autentisering / `3` serverfel /
  `4` hastighetsbegränsad / `5` hittades inte. Agenter kan förgrena logiken baserat på dessa koder
  utan att tolka felmeddelanden på naturligt språk.
* **Inga interaktiva uppmaningar i headless-miljöer.** Skicka `--yes` (eller `-y`) till
  destruktiva kommandon; skicka `--api-key` eller ange `OMI_API_KEY` för att hoppa över interaktiv inloggning.
* **Förlåtande återförsöksbeteende.** `429` och `5xx` försöks automatiskt igen med backoff
  innan fel returneras.

## Autentisering (engångsinställning av människa)

Användaren hämtar en utvecklar-API-nyckel från Omi-webbappen
(`https://app.omi.me` → Developer → API Keys) och kör något av följande:

```bash
omi auth login                          # interaktiv inklistring; nyckeln sparas inte i skalhistoriken
# eller
export OMI_API_KEY=omi_dev_...          # tillfällig, container-vänlig
```

## De fem saker agenter gör oftast

### 1. Läsa minnen

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Skapa ett minne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Läsa konversationer

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Läsa öppna åtgärdspunkter

```bash
omi action-item list --json --open
```

### 5. Markera en åtgärdspunkt som slutförd

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalt Desktop-API

När Omi Desktop exponerar sitt lokala API kan agenter fråga skärmhistorik,
sammanfattningar, SQL och uppgifter direkt på enheten utan att anropa molnets dev-API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# eller för tillfälliga sessioner:
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

Slutför eller ta endast bort uppgifter när användaren uttryckligen ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` sparar skärmdumpen på disken och
fortsätter skriva ut JSON till stdout för skript. Skärmdumps-ID kommer oftast från
`local search-screen` eller SQL mot tabellen `screenshots`. Om Desktop returnerar ett strukturerat
fel som `screenshot_pending`, `screenshot_file_missing` eller `screenshot_chunk_corrupted`,
bevarar JSON-läget fälten `reason`, `hint` och `screenshot_id` på stderr så att agenter kan
försöka igen med ett äldre ID eller rapportera det exakta hindret. Validera lyckade filer med
`file PATH` innan de skickas till synverktyg.

## Praktiskt exempel: Python-agentslinga

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

## Hantering av hastighetsbegränsningar (rate limits)

Minnen: 120/tim. Konversationer: 25/tim. Batchskapande: 15/tim.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Använd `--profile <namn>` om din agent hanterar flera Omi-konton. Varje profil
  har sina egna autentiseringsuppgifter och sin egen API-bas.
* Använd `--api-base http://localhost:8080` för lokal backend-testning.
* Använd `OMI_LOCAL_API_URL` och `OMI_LOCAL_TOKEN` för att åsidosätta profilens lokala
  Desktop API-inställningar för en enskild körning.
* Använd `--verbose` för felsökning — det loggar `METHOD path → status (Ns)` till stderr
  utan att påverka stdout, så JSON-läget förblir giltigt.
* För att skicka innehåll till en konversation via pipe, använd `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
