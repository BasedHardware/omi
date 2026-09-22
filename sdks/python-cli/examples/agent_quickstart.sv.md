# omi-cli för agents

> Praktisk guide för LLM-driven harnesses (Claude Code, Cursor, dina egna bots).

## Varför CLI:n är agentvänlig

* **Stabil JSON-kontrakt.** `--json` skriver ut ett giltigt JSON-dokument till stdout och
  *bara* ett JSON-dokument — inga framstegsmeddelanden, inga spinners. Fel går till
  stderr som `{"error": "...", "detail": "..."}`.
* **Stabila exit-koder.** `0` ok / `1` användning / `2` auth / `3` server / `4`
  rate limited / `5` inte hittad. Agents kan grensa på dessa utan att tolka
  fel på naturligt språk.
* **Inga interaktiva prompts i headless-miljöer.** Skicka `--yes` (eller `-y`) till
  destruktiva kommandon; skicka `--api-key` eller sätt `OMI_API_KEY` för att hoppa
  över interaktiv inloggning.
* **Eftergiftsbenädd retry-beteende.** `429` och `5xx` försöks igen med backoff
  innan de ytras.

## Auth (en gång, av människan)

Användaren hämtar en dev API-nyckel från Omi-webbappen
(`https://app.omi.me` → Developer → API Keys) och antingen:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## De fem sakerna agents gör oftast

### 1. Läs memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Skapa en memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Läs konversationer

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Läs öppna action items

```bash
omi action-item list --json --open
```

### 5. Markera en action item som klar

```bash
omi action-item complete --json a1b2c3d4
```

## Lokal Desktop API

När Omi Desktop exponerar sin lokala API kan agents fråga om enhetens skärminne,
recaps, SQL och uppgifter utan att använda molnets dev API:

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

Slutför eller radera uppgifter bara när användaren uttryckligen ber om det:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` skriver skärmbilden till
disk och skriver fortfarande JSON till stdout för skript. Skärm-ID:t kommer
vanligtvis från `local search-screen` eller SQL över `screenshots`-tabellen.
Om Desktop returnerar en strukturerad feltyp som `screenshot_pending`,
`screenshot_file_missing` eller `screenshot_chunk_corrupted` bevarar JSON-läge
fälten `reason`, `hint` och `screenshot_id` på stderr så att agents kan försöka
med ett äldre ID eller rapportera den exakta hindret. Validera lyckade utdata
med `file PATH` innan du skickar dem till vision-verktyg.

## Genomgående exempel: Python agent loop

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

## Hantering av rate limits

Memories: 120/tim. Konversationer: 25/tim. Batchskapande: 15/tim.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tips

* Använd `--profile <namn>` om din agent hanterar flera Omi-konton. Varje
  profil har egna credentials och API base.
* Använd `--api-base http://localhost:8080` för lokal backend-testning.
* Använd `OMI_LOCAL_API_URL` och `OMI_LOCAL_TOKEN` för att åsidosätta
  profil-lokala Desktop API-inställningar för ett körning.
* Använd `--verbose` för felsökning — den loggar `METHOD path → status (Ns)` till stderr
  utan att påverka stdout, så JSON-läget förblir giltigt.
* För att pipa innehåll till en konversation, använd `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
