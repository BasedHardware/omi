# omi-cli pro agenty

> Praktický průvodce pro LLM řízené harnessy (Claude Code, Cursor, vlastní boty).

## Proč je CLI přátelské k agentům

* **Stabilní JSON kontrakt.** `--json` vypisuje platný JSON dokument na stdout a
  *pouze* JSON dokument — žádné zprávy o průběhu, žádné spinery. Chyby jdou na
  stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilní exit kódy.** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` nenalezeno. Agenti mohou větvení bez parsování
  chyb v přirozeném jazyce.
* **Žádné interaktivní prompty v headless kontextech.** Předej `--yes` (nebo `-y`)
  destruktivním příkazům; předej `--api-key` nebo nastav `OMI_API_KEY` pro přeskočení
  interaktivního přihlášení.
* **Odpouštějící chování při opakování.** `429` a `5xx` se před zobrazením opakují
  s backoffem.

## Auth (jednorázově, člověkem)

Uživatel získá dev API klíč z Omi webové aplikace
(`https://app.omi.me` → Developer → API Keys) a buď:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Pět věcí, které agenti dělají nejčastěji

### 1. Čtení vzpomínek

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Vytvoření vzpomínky

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čtení konverzací

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čtení otevřených action items

```bash
omi action-item list --json --open
```

### 5. Označení action item jako hotové

```bash
omi action-item complete --json a1b2c3d4
```

## Místní Desktop API

Když Omi Desktop vystaví své místní API, agenti mohou dotazovat historii obrazovky
zařízení, recap, SQL a úkoly bez použití cloud dev API:

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

Úkoly dokončuj nebo maž pouze když uživatel jasně požádá:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímek obrazovky na
disk a stále vypisuje JSON na stdout pro skripty. ID snímku obvykle pochází z
`local search-screen` nebo SQL přes tabulku `screenshots`. Pokud Desktop vrátí
strukturovanou chybu jako `screenshot_pending`, `screenshot_file_missing`
nebo `screenshot_chunk_corrupted`, JSON mód zachová pole `reason`, `hint` a
`screenshot_id` na stderr, aby agenti mohli zkusit starší ID nebo nahlásit
přesný blokující důvod. Úspěšné výstupy ověř pomocí `předáním` `file PATH`
nástrojům pro vision.

## Praktický příklad: Python agent smyčka

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

## Zpracování rate limitů

Vzpomínky: 120/hod. Konverzace: 25/hod. Dávkové vytváření: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použij `--profile <jméno>` pokud tvůj agent spravuje více Omi účtů. Každý
  profil má vlastní přihlašovací údaje a API base.
* Použij `--api-base http://localhost:8080` pro lokální testování backendu.
* Použij `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` pro přepsání profilově lokálních
  Desktop API nastavení pro jeden běh.
* Použij `--verbose` pro ladění — loguje `METHOD path → status (Ns)` na stderr
  bez ovlivnění stdout, takže JSON mód zůstává platný.
* Pro pipování obsahu do konverzace použij `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
