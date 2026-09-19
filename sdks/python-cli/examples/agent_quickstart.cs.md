# omi-cli pro agenty

> Praktická příručka pro LLM prostředí (Claude Code, Cursor, vlastní boti).

## Proč je CLI vhodné pro agenty

* **Stabilní JSON rozhraní.** Přepínač `--json` vypisuje na stdout platný dokument JSON a *pouze* dokument JSON — žádné stavové zprávy ani indikátory průběhu. Chyby směřují na stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilní návratové kódy.** `0` v pořádku / `1` chybné použití / `2` ověření / `3` server / `4` překročen limit požadavků / `5` nenalezeno. Agenti se podle nich mohou větvit bez nutnosti parsovat chybové hlášky v přirozeném jazyce.
* **Žádné interaktivní dotazy v bezhlavém režimu.** K destruktivním příkazům předejte `--yes` (nebo `-y`); předejte `--api-key` nebo nastavte `OMI_API_KEY`, abyste přeskočili interaktivní přihlášení.
* **Odolné chování při opakování.** Kódy `429` a `5xx` se před vrácením automaticky opakují s exponenciálním odstupem.

## Autentizace (jednorázově, provádí člověk)

Uživatel získá vývojářský API klíč ve webové aplikaci Omi (`https://app.omi.me` → Developer → API Keys) a provede jedno z následujícího:

```bash
omi auth login                          # interaktivní vložení; klíč se neuloží do historie shellu
# nebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pro kontejnery
```

## Pět nejčastějších činností agentů

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

### 4. Čtení otevřených úkolů

```bash
omi action-item list --json --open
```

### 5. Označení úkolu jako dokončeného

```bash
omi action-item complete --json a1b2c3d4
```

## Lokální Desktop API

Když Omi Desktop zpřístupní své lokální API, agenti mohou dotazovat historii obrazovky na zařízení, přehledy, SQL a úkoly bez použití cloudového dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# nebo pro dočasné relace:
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

Úkoly dokončujte nebo mazejte pouze tehdy, když o to uživatel výslovně požádá:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímek obrazovky na disk a pro skripty stále vypisuje JSON na stdout. ID snímku obvykle pochází z `local search-screen` nebo SQL dotazu nad tabulkou `screenshots`. Pokud Desktop vrátí strukturovanou chybu, jako je `screenshot_pending`, `screenshot_file_missing` nebo `screenshot_chunk_corrupted`, režim JSON zachová pole `reason`, `hint` a `screenshot_id` na stderr, takže agenti mohou zkusit starší ID nebo nahlásit přesnou překážku. Před předáním do nástrojů vidění ověřte úspěšný výstup pomocí `file PATH`.

## Praktický příklad: Python smyčka agenta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Spustí omi CLI v režimu JSON a vyvolá výjimku při neúspěšném návratovém kódu."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI v režimu JSON tiskne strukturované chyby na stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi skončilo s kódem {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Přečte všechny otevřené úkoly a označí ty starší než 30 dní jako dokončené.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Zpracování limitů požadavků

Vzpomínky: 120/h. Konverzace: 25/h. Dávkové vytváření: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # překročen limit požadavků
    err = json.loads(result.stderr)
    # err["detail"] vypadá jako: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použijte `--profile <název>`, pokud váš agent spravuje více účtů Omi. Každý profil má vlastní přihlašovací údaje a základnu API.
* Použijte `--api-base http://localhost:8080` pro lokální testování backendu.
* Použijte `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` pro jednorázové přepsání nastavení lokálního Desktop API v profilu.
* Použijte `--verbose` pro ladění — zaznamenává `METHOD path → status (Ns)` na stderr bez ovlivnění stdout, takže režim JSON zůstává platný.
* Pro přesměrování obsahu do konverzace pomocí roury použijte `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
