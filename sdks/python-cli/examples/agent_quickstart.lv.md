# omi-cli AI aģentiem

> Praktisks ceļvedis LLM vadītām sistēmām (Claude Code, Cursor, pielāgotiem botiem).

## Kāpēc CLI ir draudzīga aģentiem

* **Stabils JSON līgums.** Karodziņš `--json` izvada derīgu JSON dokumentu uz stdout un
  *tikai* JSON dokumentu — bez progresa ziņojumiem, bez ielādes animācijām. Kļūdas tiek
  nosūtītas uz stderr formātā `{"error": "...", "detail": "..."}`.
* **Stabili izejas kodi.** `0` labi / `1` lietošanas kļūda / `2` autentifikācija / `3` servera kļūda /
  `4` pārsniegts pieprasījumu limits / `5` nav atrasts. Aģenti var tieši sazaroties, pamatojoties
  uz šiem kodiem, neveicot dabiskās valodas kļūdu parsēšanu.
* **Nav interaktīvu uzvedņu headless kontekstos.** Nododiet `--yes` (vai `-y`) destruktīvām
  komandām; nododiet `--api-key` vai iestatiet vidi `OMI_API_KEY`, lai izlaistu interaktīvo
  pieteikšanos.
* **Iecietīga atkārtotu mēģinājumu darbība.** `429` un `5xx` kļūdas tiek automātiski mēģinātas
  atkārtoti ar eksponenciālu aizturi (backoff), pirms tās tiek paziņotas.

## Autentifikācija (vienreizēja, veic cilvēks)

Lietotājs iegūst izstrādātāja API atslēgu Omi tīmekļa lietotnē
(`https://app.omi.me` → Developer → API Keys) un veic vienu no darbībām:

```bash
omi auth login                          # interaktīva ielīmēšana; atslēga netiek saglabāta čaulas vēsturē
# vai
export OMI_API_KEY=omi_dev_...          # īslaicīgs, piemērots konteineriem
```

## Piecas biežākās aģentu darbības

### 1. Lasīt atmiņas

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Izveidot atmiņu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lasīt sarunas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lasīt atvērtos darbību vienumus

```bash
omi action-item list --json --open
```

### 5. Atzīmēt darbības vienumu kā pabeigtu

```bash
omi action-item complete --json a1b2c3d4
```

## Lokālā Desktop API

Kad Omi Desktop nodrošina savu lokālo API, aģenti var pieprasīt ierīces ekrāna vēsturi,
kopsavilkumus, SQL datus un uzdevumus bez mākoņa izstrādātāju API izmantošanas:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# vai īslaicīgām sesijām:
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

Pabeidziet vai dzēsiet uzdevumus tikai tad, ja lietotājs to skaidri pieprasa:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Komanda `omi local screenshot SCREENSHOT_ID --output PATH` saglabā ekrānuzņēmumu diskā
un turpina izvadīt JSON uz stdout skriptu vajadzībām. Ekrānuzņēmuma ID parasti iegūst no
`local search-screen` vai SQL vaicājuma tabulā `screenshots`. Ja Desktop atgriež strukturētu
kļūdu, piemēram, `screenshot_pending`, `screenshot_file_missing` vai `screenshot_chunk_corrupted`,
JSON režīms saglabā laukus `reason`, `hint` un `screenshot_id` uz stderr, lai aģenti varētu mēģināt
vecāku ID vai ziņot par precīzu šķērsli. Pirms izvadīto failu nodošanas datorredzes rīkiem
pārbaudiet tos ar komandu `file PATH`.

## Praktisks piemērs: Python aģenta cikls

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

## Pieprasījumu ierobežojumu pārvaldība (Rate limits)

Atmiņas: 120/stundā. Sarunas: 25/stundā. Partijas izveide: 15/stundā.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Padomi

* Izmantojiet `--profile <name>`, ja jūsu aģents pārvalda vairākus Omi kontus. Katram
  profilam ir savi akreditācijas dati un API bāze.
* Izmantojiet `--api-base http://localhost:8080` lokālai aizmugursistēmas testēšanai.
* Izmantojiet `OMI_LOCAL_API_URL` un `OMI_LOCAL_TOKEN`, lai aizstātu profila lokālos
  Desktop API iestatījumus vienam izpildes gadījumam.
* Izmantojiet `--verbose` atkļūdošanai — tas reģistrē `METHOD path → status (Ns)` uz stderr,
  neietekmējot stdout, tāpēc JSON režīms paliek derīgs.
* Satura ievadīšanai sarunā izmantojiet `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
