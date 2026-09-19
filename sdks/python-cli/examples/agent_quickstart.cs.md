# omi-cli pro agenty

> Praktická příručka pro prostředí řízená LLM (Claude Code, Cursor, vaši vlastní boti).

## Proč je CLI přívětivé pro agenty

* **Stabilní JSON kontrakt.** Přepínač `--json` odesílá na stdout platný JSON dokument a *pouze* JSON dokument — žádné zprávy o průběhu ani indikátory načítání (spinnery). Chyby jsou odesílány na stderr ve formátu `{"error": "...", "detail": "..."}`.
* **Stabilní návratové kódy.** `0` úspěch / `1` chyba použití / `2` chyba ověření / `3` chyba serveru / `4` překročen limit požadavků (rate limited) / `5` nenalezeno. Agenti se mohou na základě těchto kódů snadno větvit bez nutnosti parsovat chybové zprávy v přirozeném jazyce.
* **Žádné interaktivní výzvy v headless kontextech.** Pro destruktivní příkazy předejte `--yes` (nebo `-y`); předejte `--api-key` nebo nastavte proměnnou prostředí `OMI_API_KEY` pro přeskočení interaktivního přihlášení.
* **Tolerantní chování při opakování.** Chyby `429` a `5xx` se před vrácením volajícímu automaticky opakují s exponenciálním zpožděním (exponential backoff).

## Autentizace (jednorázově, člověkem)

Uživatel získá vývojářský API klíč z webové aplikace Omi (`https://app.omi.me` → Developer → API Keys) a provede jednu z následujících akcí:

```bash
omi auth login                          # interaktivní vložení; klíč se neuloží do historie shellu
# nebo
export OMI_API_KEY=omi_dev_...          # dočasná relace, vhodné pro kontejnery
```

## Pět nejčastějších operací, které agenti provádějí

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

### 4. Čtení otevřených položek akcí

```bash
omi action-item list --json --open
```

### 5. Označení položky akce jako dokončené

```bash
omi action-item complete --json a1b2c3d4
```

## Místní Desktop API

Když Omi Desktop zpřístupní své místní API, agenti mohou dotazovat historii obrazovky na zařízení, souhrny, SQL a úkoly bez použití cloudového vývojářského API:

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

Úkoly dokončujte nebo odstraňujte pouze tehdy, když o to uživatel výslovně požádá:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Příkaz `omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímek obrazovky na disk a pro skripty stále tiskne JSON na stdout. ID snímku obvykle pochází z `local search-screen` nebo SQL dotazu nad tabulkou `screenshots`. Pokud Desktop vrátí strukturovanou chybu, jako je `screenshot_pending`, `screenshot_file_missing` nebo `screenshot_chunk_corrupted`, režim JSON zachovává pole `reason`, `hint` a `screenshot_id` na stderr, aby agenti mohli zopakovat pokus se starším ID nebo nahlásit přesnou překážku. Před předáním do nástrojů počítačového vidění ověřte úspěšné výstupy pomocí `file PATH`.

## Praktický příklad: Python smyčka agenta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Zavolá omi CLI v režimu JSON a při neúspěšných návratových kódech vyvolá výjimku."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI tiskne v režimu JSON strukturované chyby na stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Přečte všechny otevřené položky akcí a označí jako dokončené vše starší než 30 dní.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Zvládání limitů požadavků

Vzpomínky: 120/hod. Konverzace: 25/hod. Dávkové vytváření: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limit požadavků dosažen
    err = json.loads(result.stderr)
    # err["detail"] vypadá jako: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použijte `--profile <name>`, pokud váš agent spravuje více účtů Omi. Každý profil má své vlastní přihlašovací údaje a základní adresu API.
* Pro místní testování backendu použijte `--api-base http://localhost:8080`.
* Použijte `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` k přepsání místních nastavení Desktop API profilu pro jeden běh.
* Pro ladění použijte `--verbose` — protokoluje `METHOD path → status (Ns)` na stderr bez ovlivnění stdout, takže režim JSON zůstává platný.
* Chcete-li předat obsah do konverzace přes rouru, použijte `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
