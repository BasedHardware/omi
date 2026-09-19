# omi-cli pro agenty

> Praktická příručka pro systémy řízené LLM (Claude Code, Cursor, vlastní boti).

## Proč je CLI přívětivé pro agenty

* **Stabilní kontrakt JSON.** Přepínač `--json` vypisuje na stdout platný dokument JSON a
  *pouze* dokument JSON — žádné stavové zprávy, žádné animace načítání. Chyby jsou odesílány na
  stderr jako `{"error": "...", "detail": "..."}`.
* **Stabilní návratové kódy.** `0` úspěch / `1` chyba použití / `2` ověření / `3` chyba serveru /
  `4` překročen limit požadavků / `5` nenalezeno. Agenti se mohou větvit podle těchto kódů
  bez nutnosti analyzovat textové chyby v přirozeném jazyce.
* **Žádné interaktivní výzvy v bezhlavém (headless) prostředí.** U destruktivních příkazů předejte
  `--yes` (nebo `-y`); předejte `--api-key` nebo nastavte `OMI_API_KEY`, abyste přeskočili interaktivní přihlášení.
* **Tolerantní chování při opakování.** Chyby `429` a `5xx` se před vrácením automaticky
  opakují s exponenciálním odstupem (backoff).

## Autentizace (jednorázově, provede člověk)

Uživatel získá vývojářský klíč API z webové aplikace Omi
(`https://app.omi.me` → Developer → API Keys) a provede jednu z možností:

```bash
omi auth login                          # interaktivní vložení; klíč se neuloží do historie shellu
# nebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pro kontejnery
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

### 4. Čtení otevřených úkolů

```bash
omi action-item list --json --open
```

### 5. Označení úkolu jako dokončeného

```bash
omi action-item complete --json a1b2c3d4
```

## Místní Desktop API

Když aplikace Omi Desktop zpřístupní své místní API, agenti mohou dotazovat historii obrazovky,
rekapitulace, SQL a úkoly přímo v zařízení bez použití cloudového dev API:

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

Příkaz `omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímek obrazovky na disk a
stále tiskne JSON na stdout pro skripty. ID snímku obrazovky obvykle pochází z
`local search-screen` nebo dotazu SQL nad tabulkou `screenshots`. Pokud Desktop vrátí
strukturovanou chybu, jako je `screenshot_pending`, `screenshot_file_missing` nebo
`screenshot_chunk_corrupted`, režim JSON zachová pole `reason`, `hint` a `screenshot_id`
na stderr, takže agenti mohou zkusit starší ID nebo přesně nahlásit překážku.
Před předáním do vizuálních nástrojů ověřte úspěšné soubory pomocí `file PATH`.

## Praktický příklad: smyčka agenta v Pythonu

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

## Zvládání limitů četnosti (rate limits)

Vzpomínky: 120/hod. Konverzace: 25/hod. Hromadné vytváření: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použijte `--profile <název>`, pokud váš agent spravuje více účtů Omi. Každý profil
  má své vlastní přihlašovací údaje a základní adresu URL API.
* Pro místní testování backendu použijte `--api-base http://localhost:8080`.
* Použijte `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` pro přepsání nastavení místního
  Desktop API profilu pro jeden běh.
* Pro ladění použijte `--verbose` — zaznamenává `METHOD path → status (Ns)` na stderr
  bez ovlivnění stdout, takže režim JSON zůstává platný.
* Pro předání obsahu do konverzace prostřednictvím roury použijte `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
