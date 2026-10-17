# omi-cli pro agenty

> Praktický průvodce pro LLM-řízené harnessy (Claude Code, Cursor, vlastní boti).

## Proč je CLI přátelské agentům

* **Stabilní JSON kontrakt.** `--json` vypíše na stdout platný JSON dokument a *pouze* JSON — žádné průběhové zprávy ani spinnéry. Chyby jdou na stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilní exit kódy.** `0` ok / `1` použití / `2` auth / `3` server / `4` rate limited / `5` nenalezeno. Agenti mohou na nich větvit bez parsování chyb v přirozeném jazyce.
* **Žádné interaktivní prompty v headless kontextech.** Destruktivním příkazům předejte `--yes` (nebo `-y`); předat `--api-key` nebo nastavte `OMI_API_KEY` pro přeskočení interaktivního přihlášení.
* **Shovívavé opakování.** `429` a `5xx` se opakují s backoffem dříve, než se projeví.

## Autentizace (jednorázově, člověkem)

Uživatel získá dev API klíč z webové aplikace Omi
(`https://app.omi.me` → Developer → API Keys) a buď:

```bash
omi auth login                          # interaktivní vložení; klíč ne v shell historii
# # nebo
export OMI_API_KEY=omi_dev_...          # efemérní, vhodné pro kontejnery
```

## Pět nejčastějších věcí, které agenti dělají

### 1. Číst memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Vytvořit memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Číst conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Číst otevřené action items

```bash
omi action-item list --json --open
```

### 5. Označit action item jako hotový

```bash
omi action-item complete --json a1b2c3d4
```

## Lokální Desktop API

Když Omi Desktop vystaví své lokální API, agenti mohou dotazovat
on-device screen history, recapy, SQL a úkoly bez cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # nebo, pro efemérní sezení:
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

Úkoly dokončujte nebo mažte jen když uživatel výslovně žádá:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapíše screenshot na
disk a stále tiskne JSON na stdout pro skripty. ID screenshotu obvykle pochází
z `local search-screen` nebo SQL nad tabulkou `screenshots`. Pokud Desktop vrátí
strukturovanou chybu jako `screenshot_pending`, `screenshot_file_missing` nebo
`screenshot_chunk_corrupted`, režim JSON zachovává na stderr pole `reason`, `hint`
a `screenshot_id`, takže agent může zkusit starší ID nebo nahlásit přesný
blokér. Úspěšné výstupy ověřte `file PATH` před předáním vision nástrojům.

## Vypracovaný příklad: Python agentní smyčka

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

# Přečtěte všechny otevřené action items a označte starší než 30 dnů jako hotové.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Zvládání rate limitů

Memories: 120/hod. Conversations: 25/hod. Dávková vytvoření: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] vypadá takto: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použijte `--profile <name>` pokud agent žongluje více Omi účty. Každý
  profil má vlastní credentials a API base.
* Použijte `--api-base http://localhost:8080` pro lokální testování backendu.
* Použijte `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` pro přepsání profilových
  nastavení Desktop API na jedno spuštění.
* Použijte `--verbose` pro ladění — loguje `METHOD path → status (Ns)` na
  stderr bez vlivu na stdout, takže režim JSON zůstává platný.
* Pro pipování obsahu do conversation použijte `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
