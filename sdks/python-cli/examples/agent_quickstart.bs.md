# omi-cli za agente

> Praktični vodič za sustave pokretane LLM-om (Claude Code, Cursor, vaši vlastiti botovi).

## Zašto je CLI prijateljski prema agentima

* **Stabilan JSON ugovor.** `--json` ispisuje važeću JSON dokumentaciju na stdout i
  *samo* JSON dokumentaciju — bez poruka o napretku, bez spinnera. Pogreške idu na
  stderr kao `{"error": "...", "detail": "..."}`.
* **Stabilni izlazni kodovi.** `0` uspjeh / `1` uporaba / `2` autentifikacija /
  `3` poslužitelj / `4` ograničenje brzine / `5` nije pronađeno. Agenti se mogu
  granati na temelju njih bez parsiranja pogrešaka na prirodnom jeziku.
* **Nema interaktivnih upita u headless kontekstima.** Proslijedite `--yes` (ili `-y`) za
  destruktivne naredbe; proslijedite `--api-key` ili postavite `OMI_API_KEY` da
  preskočite interaktivnu prijavu.
* **Oprostivo ponašanje pri ponavljanju.** `429` i `5xx` se ponavljaju s povlačenjem
  prije nego što se pojave.

## Autentifikacija (jednokratna, od strane čovjeka)

Korisnik dobiva razvojni API ključ iz Omi web aplikacije
(`https://app.omi.me` → Developer → API Keys) i zatim:

```bash
omi auth login                          # interaktivno lijepljenje; ključ nije u povijesti ljuske
# ili
export OMI_API_KEY=omi_dev_...          # privremeno, pogodno za kontejnere
```

## Pet stvari koje agenti najčešće rade

### 1. Čitanje memorija

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Stvaranje memorije

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čitanje razgovora

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čitanje otvorenih stavki akcija

```bash
omi action-item list --json --open
```

### 5. Označavanje stavke akcije kao dovršene

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Kada Omi Desktop izloži svoj lokalni API, agenti mogu upitati povijest zaslona na
uređaju, sažetke, SQL i zadatke bez korištenja cloud razvojnog API-ja:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ili, za privremene sesije:
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

Zadatke dovršavajte ili brišite samo kada korisnik to jasno zatraži:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` zapisuje snimku zaslona na disk i
i dalje ispisuje JSON na stdout za skripte. ID snimke obično dolazi iz `local
search-screen` ili SQL upita nad tablicom `screenshots`. Ako Desktop vrati
strukturiranu pogrešku poput `screenshot_pending`, `screenshot_file_missing` ili
`screenshot_chunk_corrupted`, JSON mod čuva polja `reason`, `hint` i `screenshot_id`
na stderr kako bi agenti mogli ponoviti sa starijim ID-jem ili prijaviti točan
problem. Provjerite uspješne rezultate s `file PATH` prije nego ih proslijedite
alatima za vid.

## Radni primjer: Python agentska petlja

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Poziva omi CLI u JSON modu, bacajući iznimku na neuspješne izlazne kodove."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ispisuje strukturirane pogreške na stderr u JSON modu:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Pročitaj sve otvorene stavke akcija i označi one starije od 30 dana kao dovršene.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rukovanje ograničenjima brzine

Memorije: 120/sat. Razgovori: 25/sat. Skupno stvaranje: 15/sat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ograničenje brzine
    err = json.loads(result.stderr)
    # err["detail"] izgleda otprilike: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Savjeti

* Koristite `--profile <name>` ako vaš agent upravlja s više Omi računa. Svaki
  profil ima vlastite vjerodajnice i API bazu.
* Koristite `--api-base http://localhost:8080` za lokalno testiranje pozadine.
* Koristite `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` za nadjačavanje postavki
  Desktop API-ja po profilu za jednu izvedbu.
* Koristite `--verbose` za otklanjanje pogrešaka — bilježi `METHOD path → status (Ns)`
  na stderr bez utjecaja na stdout, tako da JSON mod ostaje važeći.
* Za prosljeđivanje sadržaja u razgovor koristite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```