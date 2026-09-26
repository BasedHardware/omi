# omi-cli pro agenty

> Praktická příručka pro prostředí řízená modely LLM (Claude Code, Cursor, vlastní boti).

## Proč je CLI přívětivé pro agenty

* **Stabilní kontrakt JSON.** Přepínač `--json` vygeneruje na stdout platný dokument JSON a
  *výhradně* dokument JSON — žádné stavové zprávy, žádné animované indikátory. Chybové výstupy směřují na
  stderr ve formátu `{"error": "...", "detail": "..."}`.
* **Stabilní návratové kódy.** `0` v pořádku / `1` chybné použití / `2` selhání autentizace / `3` chyba serveru / `4` překročen
  limit požadavků (rate limited) / `5` nenalezeno. Agenti se mohou na základě těchto kódů rozhodovat, aniž by museli analyzovat textové chyby v přirozeném jazyce.
* **Žádné interaktivní výzvy v bezhlavých (headless) kontextech.** Pro destruktivní
  příkazy předejte `--yes` (nebo `-y`); předejte `--api-key` nebo nastavte `OMI_API_KEY`, abyste přeskočili
  interaktivní přihlášení.
* **Tolerantní chování při opakování.** Chybové stavy `429` a `5xx` se před ohlášením automaticky
  opakují s exponenciálním odstupem (backoff).

## Autentizace (jednorázově, provádí člověk)

Uživatel získá vývojářský API klíč ve webové aplikaci Omi
(`https://app.omi.me` → Developer → API Keys) a zvolí jednu z možností:

```bash
omi auth login                          # interaktivní vložení; klíč nezůstává v historii shellu
# nebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pro kontejnery
```

## Pět nejčastějších úkonů agentů

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

Pokud Omi Desktop vystavuje své lokální API, agenti mohou dotazovat historii
obrazovky na zařízení, souhrny, SQL dotazy a úkoly bez vytěžování cloudového vývojářského API:

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

Úkoly dokončujte nebo mazejte pouze na výslovnou žádost uživatele:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Příkaz `omi local screenshot SCREENSHOT_ID --output PATH` uloží snímek obrazovky na
disk a pro potřeby skriptů nadále vypisuje JSON na stdout. ID snímku obvykle
pochází z `local search-screen` nebo SQL dotazu nad tabulkou `screenshots`. Pokud Desktop
vrátí strukturovanou chybu, jako je `screenshot_pending`, `screenshot_file_missing` nebo
`screenshot_chunk_corrupted`, režim JSON zachová pole `reason`, `hint` a
`screenshot_id` na stderr, takže agenti mohou zkusit starší ID nebo nahlásit přesnou
příčinu selhání. Úspěšné soubory před předáním nástrojům pro počítačové vidění ověřte pomocí `file PATH`.

## Praktický příklad: smyčka agenta v Pythonu

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Spustí omi CLI v režimu JSON, při nenulovém návratovém kódu vyvolá výjimku."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI v režimu JSON vypisuje strukturované chyby na stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi skončilo s kódem {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Přečte všechny otevřené úkoly a označí za dokončené ty, které jsou starší než 30 dní.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Řízení limitů požadavků (Rate limits)

Vzpomínky: 120/hod. Konverzace: 25/hod. Hromadná vytvoření: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limit požadavků překročen
    err = json.loads(result.stderr)
    # err["detail"] vypadá takto: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použijte `--profile <name>`, pokud váš agent spravuje více účtů Omi. Každý
  profil má vlastní přihlašovací údaje i základnu API.
* Pro testování s lokálním backendem použijte `--api-base http://localhost:8080`.
* Pro jednorázové přepsání lokálních nastavení Desktop API v profilu použijte
  `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN`.
* Pro ladění použijte `--verbose` — zaznamenává `METHOD cesta → stav (Ns)` na stderr
  bez ovlivnění stdout, takže formát JSON zůstává platný.
* Pro přesměrování obsahu do konverzace pomocí roury (pipe) použijte `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
