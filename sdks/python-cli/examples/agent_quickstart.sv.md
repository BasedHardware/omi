# omi-cli för agenter

> Praktisk guide för LLM-drivna miljöer (Claude Code, Cursor, dina egna botar).

## Varför detta CLI är agentvänligt

* **Stabilt JSON-kontrakt.** Flaggan `--json` matar ut ett giltigt JSON-dokument till stdout och *endast* ett JSON-dokument — inga förloppsmeddelanden, inga laddningsindikatorer (spinners). Fel skickas till stderr som `{"error": "...", "detail": "..."}`.
* **Stabila slutkoder.** `0` lyckades / `1` användningsfel / `2` autentiseringsfel / `3` serverfel / `4` hastighetsbegränsning (rate limited) / `5` hittades inte. Agenter kan förgrena logik baserat på dessa koder utan att behöva analysera felmeddelanden i naturligt språk.
* **Inga interaktiva uppmaningar i headless-sammanhang.** Skicka med `--yes` (eller `-y`) för destruktiva kommandon; skicka med `--api-key` eller ange miljövariabeln `OMI_API_KEY` för att hoppa över interaktiv inloggning.
* **Förlåtande återförsöksbeteende.** Fel med `429` och `5xx` försöks automatiskt igen med exponentiell fördröjning (exponential backoff) innan de rapporteras.

## Autentisering (engångsåtgärd, av människan)

Användaren hämtar en API-nyckel för utvecklare från Omi-webbappen (`https://app.omi.me` → Developer → API Keys) och gör något av följande:

```bash
omi auth login                          # interaktiv inklistring; nyckeln sparas inte i skalets historik
# eller
export OMI_API_KEY=omi_dev_...          # tillfällig session, lämplig för containrar
```

## De fem vanligaste åtgärderna agenter utför

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

## Lokalt Desktop API

När Omi Desktop exponerar sitt lokala API kan agenter fråga skärmhistorik, sammanfattningar, SQL och uppgifter direkt på enheten utan att anropa molnets utvecklar-API:

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

Kommandot `omi local screenshot SCREENSHOT_ID --output PATH` sparar skärmdumpen på hårddisken och skriver fortfarande ut JSON till stdout för skript. Skärmdumps-ID hämtas vanligtvis från `local search-screen` eller en SQL-fråga mot tabellen `screenshots`. Om Desktop returnerar ett strukturerat fel som `screenshot_pending`, `screenshot_file_missing` eller `screenshot_chunk_corrupted`, bevarar JSON-läget fälten `reason`, `hint` och `screenshot_id` på stderr så att agenter kan försöka igen med ett äldre ID eller rapportera det exakta hindret. Validera godkända utdata med `file PATH` innan de skickas till synverktyg.

## Genomarbetat exempel: Python-agentloop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Anropar omi CLI i JSON-läge och utlöser ett undantag vid icke-noll returkoder."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI skriver strukturerade fel till stderr i JSON-läge:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Läs alla öppna åtgärdspunkter och markera allt som är äldre än 30 dagar som slutfört.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Hantering av hastighetsbegränsningar

Minnen: 120/timme. Konversationer: 25/timme. Batch-skapande: 15/timme.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # hastighetsbegränsning uppnådd
    err = json.loads(result.stderr)
    # err["detail"] ser ut som: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Använd `--profile <name>` om din agent hanterar flera Omi-konton. Varje profil har sina egna autentiseringsuppgifter och API-bas.
* Använd `--api-base http://localhost:8080` för lokal backend-testning.
* Använd `OMI_LOCAL_API_URL` och `OMI_LOCAL_TOKEN` för att åsidosätta profilens lokala Desktop API-inställningar för en enskild körning.
* Använd `--verbose` för felsökning — det loggar `METHOD path → status (Ns)` till stderr utan att påverka stdout, så att JSON-läget förblir giltigt.
* För att skicka innehåll via pipe till en konversation, använd `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
