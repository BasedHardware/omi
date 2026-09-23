# omi-cli za agente

> Praktični vodič za LLM-vođene harnessove (Claude Code, Cursor, vaši botovi).

## Zašto je CLI prijateljski prema agentima

* **Stabilan JSON ugovor.** `--json` ispisuje važeći JSON dokument na stdout i
  *samo* JSON dokument — bez poruka o napretku, bez spinnera. Pogreške idu na
  stderr kao `{"error": "...", "detail": "..."}`.
* **Stabilni exit kodovi.** `0` ok / `1` usage / `2` auth / `3` server / `4`
  rate limited / `5` nije pronađeno. Agenti mogu granati prema tome bez
  parsiranja pogrešaka na prirodnom jeziku.
* **Nema interaktivnih upita u headless kontekstima.** Proslijedi `--yes` (ili `-y`)
  destruktivnim naredbama; proslijedi `--api-key` ili postavi `OMI_API_KEY` da
  preskočiš interaktivnu prijavu.
* **Oproštajno ponašanje pri ponavljanju.** `429` i `5xx` se ponovo pokušavaju s
  backoffom prije prikaza.

## Auth (jednom, od strane čovjeka)

Korisnik dobiva dev API ključ iz Omi web aplikacije
(`https://app.omi.me` → Developer → API Keys) i ili:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Pet stvari koje agenti rade najčešće

### 1. Čitanje memorija

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Stvaranje memorije

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čitanje konverzacija

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čitanje otvorenih action itema

```bash
omi action-item list --json --open
```

### 5. Označavanje action itema kao gotovog

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Kada Omi Desktop izloži svoje lokalno API, agenti mogu pitati povijest zaslona
uređaja, recap, SQL i zadatke bez korištenja cloud dev API-ja:

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

Dovrši ili izbriši zadatke samo kada korisnik jasno zatraži:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapisuje snimku zaslona na
disk i još uvijek ispisuje JSON na stdout za skripte. ID snimke obično dolazi iz
`local search-screen` ili SQL-a nad tablicom `screenshots`. Ako Desktop vrati
strukturiranu pogrešku poput `screenshot_pending`, `screenshot_file_missing`
ili `screenshot_chunk_corrupted`, JSON način čuva polja `reason`, `hint` i
`screenshot_id` na stderru da agenti mogu pokušati stariji ID ili prijaviti
točnu blokadu. Provjeri uspješne izlaze s `file PATH` prije nego ih predaš
alatima za vision.

## Praktični primjer: Python petlja agenta

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

## Rukovanje rate limitovima

Memorije: 120/sat. Konverzacije: 25/sat. Skupno stvaranje: 15/sat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Savjeti

* Koristi `--profile <ime>` ako tvoj agent upravlja s više Omi računa. Svaki
  profil ima vlastite credentials i API base.
* Koristi `--api-base http://localhost:8080` za lokalno testiranje backend-a.
* Koristi `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` za nadjačavanje profil-lokalnih
  Desktop API postavki za jedno izvršenje.
* Koristi `--verbose` za otklanjanje grešaka — bilježi `METHOD path → status (Ns)` na stderr
  bez utjecaja na stdout, tako da JSON način ostaje valjan.
* Za slanje sadržaja u konverzaciju koristi `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
