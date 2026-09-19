# omi-cli pre agentov

> Praktická príručka pre prostredia riadené LLM (Claude Code, Cursor, vlastné boty).

## Prečo je CLI vhodné pre agentov

* **Stabilné JSON rozhranie.** Prepínač `--json` odosiela na stdout platný dokument JSON a *iba* dokument JSON — žiadne stavové správy ani indikátory priebehu. Chyby smerujú na stderr ako `{"error": "...", "detail": "..."}`.
* **Stabilné návratové kódy.** `0` v poriadku / `1` nesprávne použitie / `2` overenie / `3` server / `4` prekročený limit požiadaviek / `5` nenájdené. Agenti sa môžu rozhodovať na základe týchto kódov bez nutnosti analyzovať textové chybové správy.
* **Žiadne interaktívne výzvy v bezhlavých kontextoch.** Pre deštruktívne príkazy odovzdajte `--yes` (alebo `-y`); odovzdajte `--api-key` alebo nastavte `OMI_API_KEY` na preskočenie interaktívneho prihlásenia.
* **Tolerantné správanie pri opakovaní.** Kódy `429` a `5xx` sa pred nahlásením automaticky zopakujú s exponenciálnym odstupom.

## Autentifikácia (jednorazovo, vykonáva používateľ)

Používateľ získa vývojársky kľúč API vo webovej aplikácii Omi (`https://app.omi.me` → Developer → API Keys) a vyberie jednu z možností:

```bash
omi auth login                          # interaktívne vloženie; kľúč sa neuloží do histórie shellu
# alebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pre kontajnery
```

## Päť najčastejších činností agentov

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

### 4. Čítanie otvorených úloh

```bash
omi action-item list --json --open
```

### 5. Označenie úlohy ako dokončenej

```bash
omi action-item complete --json a1b2c3d4
```

## Lokálne Desktop API

Keď Omi Desktop sprístupní svoje lokálne API, agenti môžu dopytovať históriu obrazovky na zariadení, zhrnutia, SQL a úlohy bez použitia cloudového dev API:

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

Úlohy dokončujte alebo vymazávajte iba vtedy, keď o to používateľ výslovne požiada:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímku obrazovky na disk a pre skripty naďalej vypisuje JSON na stdout. ID snímky zvyčajne pochádza z `local search-screen` alebo SQL dopytu nad tabuľkou `screenshots`. Ak Desktop vráti štruktúrovanú chybu, ako napríklad `screenshot_pending`, `screenshot_file_missing` alebo `screenshot_chunk_corrupted`, režim JSON zachováva polia `reason`, `hint` a `screenshot_id` na stderr, takže agenti môžu skúsiť staršie ID alebo nahlásiť presnú prekážku. Pred odovzdaním vizuálnym nástrojom overte úspešné výstupy pomocou `file PATH`.

## Praktický príklad: Python slučka agenta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Spustí omi CLI v režime JSON a vyvolá výnimku pri neúspešných návratových kódoch."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI v režime JSON vypisuje štruktúrované chyby na stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi skončilo s kódom {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Prečíta všetky otvorené úlohy a označí tie staršie ako 30 dní za dokončené.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Spracovanie limitov požiadaviek

Spomienky: 120/h. Konverzácie: 25/h. Dávkové vytváranie: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # prekročený limit požiadaviek
    err = json.loads(result.stderr)
    # err["detail"] vyzerá ako: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použite `--profile <názov>`, ak váš agent spravuje viacero účtov Omi. Každý profil má vlastné poverenia a základňu API.
* Použite `--api-base http://localhost:8080` pre lokálne testovanie backendu.
* Použite `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN` na prepísanie nastavení lokálneho Desktop API pre jedno spustenie.
* Použite `--verbose` na ladenie — zaznamenáva `METHOD path → status (Ns)` na stderr bez ovplyvnenia stdout, takže režim JSON zostáva platný.
* Pre presmerovanie obsahu do konverzácie pomocou rúry použite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
