# omi-cli pre agentov

> Praktická príručka pre LLM-driven harnessy (Claude Code, Cursor, vlastné boty).

## Prečo je CLI priateľské k agentom

* **Stabilná JSON zmluva.** `--json` vypíše platný JSON dokument na stdout a
  *len* JSON dokument — žiadne správy o priebehu, žiadne spinery. Chyby idú na
  stderr ako `{"error": "...", "detail": "..."}`.
* **Stabilné exit kódy.** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` nenájdené. Agenti môžu vetviť bez parsovania
  chýb v prirodzenom jazyce.
* **Žiadne interaktívne prompty v headless kontextoch.** Pošli `--yes` (alebo `-y`)
  deštruktívnym príkazom; pošli `--api-key` alebo nastav `OMI_API_KEY` pre preskočenie
  interaktívneho prihlásenia.
* **Odpúšťajúce správanie pri opakovaní.** `429` a `5xx` sa pred zobrazením opakujú
  s backoffom.

## Auth (jednorazovo, človekom)

Používateľ získa dev API kľúč z Omi webovej aplikácie
(`https://app.omi.me` → Developer → API Keys) a buď:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Päť vecí, ktoré agenti robia najčastejšie

### 1. Čítanie spomienok

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Vytvorenie spomienky

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čítanie konverzácií

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čítanie otvorených action items

```bash
omi action-item list --json --open
```

### 5. Označenie action item ako hotovej

```bash
omi action-item complete --json a1b2c3d4
```

## Lokálne Desktop API

Keď Omi Desktop vystaví svoje lokálne API, agenti sa môžu pýtať na históriu obrazovky
zariadenia, recap, SQL a úlohy bez použitia cloud dev API:

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

Úlohy dokončuj alebo maž len keď používateľ jasne požiada:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímku obrazovky na
disk a stále vypisuje JSON na stdout pre skripty. ID snímku obvykle pochádza z
`local search-screen` alebo SQL cez tabuľku `screenshots`. Ak Desktop vráti
štruktúrovanú chybu ako `screenshot_pending`, `screenshot_file_missing`
alebo `screenshot_chunk_corrupted`, JSON mód zachová polia `reason`, `hint` a
`screenshot_id` na stderr, aby agenti mohli skúsiť staršie ID alebo nahlásiť
presný blokujúci dôvod. Úspešné výstupy over pomocou `file PATH` pred odovzdaním
nástrojom pre vision.

## Praktický príklad: Python agent slučka

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

## Spracovanie rate limitov

Spomienky: 120/hod. Konverzácie: 25/hod. Dávkové vytváranie: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použi `--profile <meno>` ak tvoj agent spravuje viac Omi účtov. Každý
  profil má vlastné prihlasovacie údaje a API base.
* Použi `--api-base http://localhost:8080` pre lokálne testovanie backendu.
* Použi `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` pre prepísanie profilovo lokálnych
  Desktop API nastavení pre jeden beh.
* Použi `--verbose` pre ladenie — loguje `METHOD path → status (Ns)` na stderr
  bez ovplyvnenia stdout, takže JSON mód zostáva platný.
* Pre pipovanie obsahu do konverzácie použi `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
