# omi-cli pre agentov

> Praktická príručka pre nástroje riadené modelmi LLM (Claude Code, Cursor, vlastné boty).

## Prečo je CLI vhodné pre agentov

* **Stabilný kontrakt JSON.** Voľba `--json` posiela na stdout platný dokument JSON a
  *výhradne* dokument JSON — žiadne stavové správy ani indikátory priebehu. Chyby sa zapisujú
  do stderr vo formáte `{"error": "...", "detail": "..."}`.
* **Stabilné návratové kódy.** `0` úspech / `1` chyba použitia / `2` overenie totožnosti / `3` chyba servera / `4` limit požiadaviek / `5` nenájdené. Agenti sa môžu podľa týchto kódov vetviť bez nutnosti spracovania prirodzeného jazyka.
* **Žiadne interaktívne výzvy v bezhlavom režime.** Pri deštruktívnych príkazoch zadajte `--yes` (alebo `-y`); zadajte `--api-key` alebo nastavte `OMI_API_KEY`, aby ste preskočili interaktívne prihlásenie.
* **Tolerantné správanie pri opakovaní.** Návratové kódy `429` a `5xx` sa pred vyvolaním chyby opakujú s postupným oneskorením.

## Autentifikácia (jednorazovo človekom)

Používateľ získa vývojársky kľúč API vo webovej aplikácii Omi
(`https://app.omi.me` → Developer → API Keys) a buď:

```bash
omi auth login                          # interaktívne vloženie; kľúč sa neuloží do histórie shellu
# alebo
export OMI_API_KEY=omi_dev_...          # dočasné, vhodné pre kontajnery
```

## Päť vecí, ktoré agenti vykonávajú najčastejšie

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

## Lokálne rozhranie Desktop API

Keď aplikácia Omi Desktop sprístupní svoje lokálne API, agenti môžu prehľadávať históriu obrazovky na zariadení,
súhrny, SQL a úlohy bez použitia cloudového API:

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

Úlohy označujte ako dokončené alebo ich mažte iba vtedy, keď o to používateľ výslovne požiada:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Príkaz `omi local screenshot SCREENSHOT_ID --output PATH` zapíše snímku obrazovky na
disk a zároveň vypíše JSON na stdout pre skripty. Identifikátor snímky obrazovky zvyčajne pochádza
z príkazu `local search-screen` alebo z dopytu SQL nad tabuľkou `screenshots`. Ak aplikácia Desktop
vráti štruktúrované zlyhanie ako `screenshot_pending`, `screenshot_file_missing`
alebo `screenshot_chunk_corrupted`, režim JSON zachová polia `reason`, `hint` a
`screenshot_id` na stderr, aby agenti mohli zopakovať pokus so starším ID alebo nahlásiť
presnú prekážku. Pred odovzdaním výstupov vizuálnym modelom overte úspešné súbory pomocou `file PATH`.

## Kompletný príklad: Slučka agenta v jazyku Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Spustí omi CLI v režime JSON a pri chybových kódoch vyvolá výnimku."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI vypisuje štruktúrované chyby do stderr v režime JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Načíta všetky otvorené úlohy a označí tie staršie ako 30 dní ako dokončené.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Spracovanie limitov požiadaviek (rate limits)

Spomienky: 120/hod. Konverzácie: 25/hod. Hromadné vytváranie: 15/hod.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # prekročený limit
    err = json.loads(result.stderr)
    # err["detail"] vyzerá takto: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Tipy

* Použite `--profile <názov>`, ak váš agent spravuje viacero účtov Omi. Každý
  profil má vlastné poverenia a základňu API.
* Na testovanie lokálneho backendu použite `--api-base http://localhost:8080`.
* Na prepísanie lokálnych nastavení Desktop API pre jedno spustenie použite
  premenné `OMI_LOCAL_API_URL` a `OMI_LOCAL_TOKEN`.
* Na ladenie použite `--verbose` — zaznamenáva `METHOD path → status (Ns)` do stderr
  bez ovplyvnenia stdout, takže režim JSON zostáva platný.
* Ak chcete poslať obsah do konverzácie cez rúru (pipe), použite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
