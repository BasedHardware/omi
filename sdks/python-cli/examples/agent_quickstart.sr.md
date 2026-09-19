# omi-cli za agente

> Praktični vodič za okruženja zasnovana na LLM-u (Claude Code, Cursor, vaši prilagođeni botovi).

## Zašto je CLI pogodan za agente

* **Stabilan JSON ugovor.** `--json` ispisuje validan JSON dokument na stdout i
  *isključivo* JSON dokument — bez poruka o napretku, bez animacija učitavanja. Greške se šalju
  na stderr u formatu `{"error": "...", "detail": "..."}`.
* **Stabilni izlazni kodovi.** `0` uspeh / `1` greška u upotrebi / `2` autentifikacija /
  `3` greška servera / `4` prekoračeno ograničenje brzine / `5` nije pronađeno. Agenti mogu granati
  logiku na osnovu ovih kodova bez parsiranja grešaka na prirodnom jeziku.
* **Bez interaktivnih upita u headless okruženjima.** Prosledite `--yes` (ili `-y`) za
  destruktivne komande; prosledite `--api-key` ili postavite `OMI_API_KEY` da preskočite interaktivno prijavljivanje.
* **Tolerantno ponašanje ponovnog pokušaja.** Greške `429` i `5xx` se automatski ponovo pokušavaju
  uz eksponencijalno odlaganje (backoff) pre nego što se vrate.

## Autentifikacija (jednokratno, od strane čoveka)

Korisnik dobija razvojni API ključ iz Omi veb aplikacije
(`https://app.omi.me` → Developer → API Keys) i primenjuje jednu od opcija:

```bash
omi auth login                          # interaktivno lepljenje; ključ se ne čuva u istoriji ljuske
# ili
export OMI_API_KEY=omi_dev_...          # privremeno, pogodno za kontejnere
```

## Pet operacija koje agenti najčešće izvršavaju

### 1. Čitanje sećanja

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Kreiranje sećanja

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čitanje razgovora

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čitanje otvorenih stavki zadataka

```bash
omi action-item list --json --open
```

### 5. Označavanje stavke zadatka završenom

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Kada Omi Desktop izloži svoj lokalni API, agenti mogu ispitivati istoriju ekrana,
rezimee, SQL i zadatke direktno na uređaju bez korišćenja dev API-ja u oblaku:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ili za privremene sesije:
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

Zadatke završavajte ili brišite samo kada to korisnik izričito zatraži:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Komanda `omi local screenshot SCREENSHOT_ID --output PATH` upisuje snimak ekrana na disk i
nastavlja da ispisuje JSON na stdout za skripte. ID snimka ekrana obično potiče iz
`local search-screen` ili SQL upita nad tabelom `screenshots`. Ako Desktop vrati strukturiranu grešku
kao što je `screenshot_pending`, `screenshot_file_missing` ili `screenshot_chunk_corrupted`,
JSON režim čuva polja `reason`, `hint` i `screenshot_id` na stderr-u, omogućavajući agentima da
pokušaju ponovo sa starijim ID-jem ili prijave tačan problem. Pre prosleđivanja vizuelnim alatima
proverite ispravnost datoteka pomoću `file PATH`.

## Praktičan primer: Python petlja agenta

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

## Upravljanje ograničenjima brzine (rate limits)

Sećanja: 120/sat. Razgovori: 25/sat. Grupno kreiranje: 15/sat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Saveti

* Koristite `--profile <naziv>` ako vaš agent upravlja sa više Omi naloga. Svaki profil
  ima sopstvene akreditive i osnovnu adresu API-ja.
* Koristite `--api-base http://localhost:8080` za lokalno testiranje serverskog dela.
* Koristite `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` za privremeno nadjačavanje lokalnih
  podešavanja Desktop API-ja profila za jedno izvršavanje.
* Koristite `--verbose` za otklanjanje grešaka — beleži `METHOD path → status (Ns)` na stderr
  bez uticaja na stdout, čime JSON režim ostaje validan.
* Za prosleđivanje sadržaja u razgovor preko cevi (pipe), koristite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
