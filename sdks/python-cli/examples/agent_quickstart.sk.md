# omi-cli pre AI agentov

> Praktická príručka pre prostredia riadené LLM (Claude Code, Cursor, vlastné boty).

## Prečo je CLI prívetivé pre agentov

* **Stabilný JSON kontrakt.** Parameter `--json` odosiela platný dokument JSON na stdout a
  *výhradne* dokument JSON — žiadne stavové správy, žiadne indikátory načítavania. Chyby sa
  odosielajú na stderr vo formáte `{"error": "...", "detail": "..."}`.
* **Stabilné návratové kódy.** `0` úspech / `1` chyba použitia / `2` autentifikácia / `3` chyba
  servera / `4` prekročenie limitu požiadaviek / `5` nenájdené. Agenti sa môžu vetviť priamo na
  základe týchto kódov bez nutnosti parsovania textových chýb v prirodzenom jazyku.
* **Žiadne interaktívne výzvy v headless kontextoch.** Pre deštruktívne príkazy zadajte `--yes`
  (alebo `-y`); zadajte `--api-key` alebo nastavte premennú prostredia `OMI_API_KEY` na preskočenie
  interaktívneho prihlásenia.
* **Tolerantné správanie pri opakovaných pokusoch.** Chyby typu `429` a `5xx` sa pred nahlásením
  automaticky znova pokúšajú s exponenciálnym oneskorením (backoff).

## Autentifikácia (jednorazová, vykonaná človekom)

Používateľ získa vývojársky API kľúč z webovej aplikácie Omi
(`https://app.omi.me` → Developer → API Keys) a buď:

```bash
omi auth login                          # interaktívne vloženie; kľúč sa neuloží do histórie shellu
# alebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pre kontajnery
```

## Päť najčastejších operácií agentov

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

### 4. Čítanie otvorených položiek akcií

```bash
omi action-item list --json --open
```

### 5. Označenie položky akcie ako dokončenej

```bash
omi action-item complete --json a1b2c3d4
```

## Lokálne Desktop API

Keď Omi Desktop sprístupní svoje lokálne API, agenti môžu dopytovať históriu obrazovky zariadenia,
súhrny, SQL a úlohy bez použitia cloudového dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# alebo pre dočasné relácie:
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

Úlohy dokončujte alebo mažte iba vtedy, keď o to používateľ výslovne požiada:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Príkaz `omi local screenshot SCREENSHOT_ID --output PATH` uloží snímku obrazovky na disk
a naďalej tlačí JSON výstup na stdout pre skripty. ID snímky obrazovky zvyčajne pochádza z
`local search-screen` alebo SQL dopytu nad tabuľkou `screenshots`. Ak Desktop vráti štruktúrované
zlyhanie, ako napríklad `screenshot_pending`, `screenshot_file_missing` alebo `screenshot_chunk_corrupted`,
režim JSON zachováva polia `reason`, `hint` a `screenshot_id` na stderr, takže agenti môžu skúsiť
staršie ID alebo nahlásiť presnú prekážku. Pred odovzdaním výstupov nástrojom počítačového videnia
overte úspešný výstup pomocou `file PATH`.

## Praktický príklad: Slučka agenta v Pythone

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

## Riešenie limitov požiadaviek (Rate Limits)

Spomienky: 120/hod. Konverzácie: 25/hod. Hromadné vytváranie: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použite `--profile <name>`, ak váš agent spravuje viacero účtov Omi. Každý
  profil má vlastné poverenia a základňu API.
* Použite `--api-base http://localhost:8080` pre lokálne testovanie backendu.
* Použite premenné prostredia `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` na prepísanie
  nastavení Desktop API špecifických pre profil na jeden beh.
* Použite `--verbose` pre ladenie — zaznamenáva `METHOD path → status (Ns)` na stderr
  bez ovplyvnenia stdout, takže režim JSON zostáva plne platný.
* Na presmerovanie obsahu do konverzácie použite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
