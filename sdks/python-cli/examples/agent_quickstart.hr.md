# omi-cli za agente

> Praktični vodič za alate pokretane LLM-om (Claude Code, Cursor, vlastiti botovi).

## Zašto je CLI prilagođen agentima

* **Stabilan JSON ugovor.** `--json` šalje valjani JSON dokument na stdout i
  *isključivo* JSON dokument — bez poruka o napretku ili animacija. Pogreške se šalju na
  stderr kao `{"error": "...", "detail": "..."}`.
* **Stabilni izlazni kodovi.** `0` u redu / `1` pogreška upotrebe / `2` autentifikacija / `3` pogreška poslužitelja / `4` ograničenje brzine / `5` nije pronađeno. Agenti se mogu granati na temelju ovih kodova bez parsiranja poruka na prirodnom jeziku.
* **Bez interaktivnih upita u radu bez sučelja.** Proslijedite `--yes` (ili `-y`) za
  destruktivne naredbe; proslijedite `--api-key` ili postavite `OMI_API_KEY` kako biste preskočili interaktivnu prijavu.
* **Tolerantno ponovno pokušavanje.** Kodovi `429` i `5xx` ponovno se pokušavaju s odgodom
  prije nego što se javi pogreška.

## Autentifikacija (jednokratno, od strane čovjeka)

Korisnik preuzima razvojni API ključ iz Omi web aplikacije
(`https://app.omi.me` → Developer → API Keys) i odabire jedno od sljedećeg:

```bash
omi auth login                          # interaktivno lijepljenje; ključ se ne sprema u povijest ljuske
# ili
export OMI_API_KEY=omi_dev_...          # privremeno, pogodno za kontejnere
```

## Pet stvari koje agenti najčešće rade

### 1. Čitanje sjećanja

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Stvaranje sjećanja

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Čitanje razgovora

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Čitanje otvorenih zadataka

```bash
omi action-item list --json --open
```

### 5. Označavanje zadatka dovršenim

```bash
omi action-item complete --json a1b2c3d4
```

## Lokalni Desktop API

Kada Omi Desktop izloži svoj lokalni API, agenti mogu pretraživati povijest zaslona na uređaju,
sažetke, SQL i zadatke bez upotrebe API-ja u oblaku:

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

Dovršavajte ili brišite zadatke samo kada korisnik to izričito zatraži:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Naredba `omi local screenshot SCREENSHOT_ID --output PATH` zapisuje snimku zaslona na
disk i dalje ispisuje JSON na stdout za skripte. ID snimke zaslona obično dolazi
iz `local search-screen` ili SQL-a nad tablicom `screenshots`. Ako Desktop
vrati strukturiranu pogrešku poput `screenshot_pending`, `screenshot_file_missing`
ili `screenshot_chunk_corrupted`, JSON način rada čuva polja `reason`, `hint` i
`screenshot_id` na stderr-u kako bi agenti mogli pokušati sa starijim ID-om ili prijaviti
točnu prepreku. Provjerite uspješne izlaze pomoću `file PATH` prije nego što ih proslijedite
vizualnim alatima.

## Detaljan primjer: Python petlja agenta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Poziva omi CLI u JSON načinu rada, podižući iznimku pri neuspjelim kodovima."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ispisuje strukturirane pogreške na stderr u JSON načinu:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Čita sve otvorene zadatke i označava dovršenim sve starije od 30 dana.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rukovanje ograničenjima brzine (rate limits)

Sjećanja: 120/sat. Razgovori: 25/sat. Skupna stvaranja: 15/sat.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ograničenje brzine
    err = json.loads(result.stderr)
    # err["detail"] izgleda ovako: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Savjeti

* Koristite `--profile <naziv>` ako vaš agent upravlja s više Omi računa. Svaki
  profil ima svoje vjerodajnice i API adresu.
* Za testiranje lokalnog pozadinskog poslužitelja koristite `--api-base http://localhost:8080`.
* Koristite `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` za poništavanje lokalnih
  Desktop API postavki profila za jedno pokretanje.
* Koristite `--verbose` za otklanjanje pogrešaka — bilježi `METHOD path → status (Ns)` na stderr
  bez utjecaja na stdout, tako da JSON način ostaje valjan.
* Za prosljeđivanje sadržaja u razgovor putem cjevovoda koristite `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
