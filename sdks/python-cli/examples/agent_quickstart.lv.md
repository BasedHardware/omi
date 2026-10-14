# omi-cli aģentiem

> Praktiskā rokasgrāmata LLM vadāmiem harnessiem (Claude Code, Cursor, jūsu pašu botiem).

## Kāpēc CLI ir draudzīgs aģentiem

* **Stabils JSON līgums.** `--json` izdod derīgu JSON dokumentu uz stdout un
  *tikai* JSON dokumentu — bez progresa ziņojumiem, bez spinneriem. Kļūdas iet
  uz stderr kā `{"error": "...", "detail": "..."}`.
* **Stabili iziešanas kodi.** `0` labi / `1` lietošana / `2` auth / `3` serveris /
  `4` ātruma ierobežojums / `5` nav atrasts. Aģenti var zaroties uz tiem bez
  dabiskās valodas kļūdu parsēšanas.
* **Nav interaktīvu uzvedņu headless kontekstos.** Nododiet `--yes` (vai `-y`)
  destruktīvām komandām; nododiet `--api-key` vai iestatiet `OMI_API_KEY`, lai
  izlaistu interaktīvo pieteikšanos.
* **Piedodama atkārtošanas uzvedība.** `429` un `5xx` tiek atkārtoti ar backoff
  pirms parādīšanās.

## Auth (vienreiz, cilvēka)

Lietotājs iegūst dev API atslēgu no Omi tīmekļa lietotnes
(`https://app.omi.me` → Developer → API Keys) un vai nu:

```bash
omi auth login                          # interaktīva ielīmēšana; atslēga nepaliek shell vēsturē
# vai
export OMI_API_KEY=omi_dev_...          # īslaicīga, ideāla konteineriem
```

## Piecas lietas, ko aģenti dara visbiežāk

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

### 4. Lasīt atvērtos rīcības punktus

```bash
omi action-item list --json --open
```

### 5. Atzīmēt rīcības punktu kā paveiktu

```bash
omi action-item complete --json a1b2c3d4
```

## Vietējā Desktop API

Kad Omi Desktop atklāj savu vietējo API, aģenti var vaicāt ierīces ekrāna
vēsturi, kopsavilkumus, SQL un uzdevumus, neizmantojot mākoņa dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# vai, īslaicīgām sesijām:
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

Pabeigt vai dzēst uzdevumus tikai tad, kad lietotājs to skaidri lūdz:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ieraksta ekrānuzņēmumu diskā
un joprojām drukā JSON uz stdout skriptiem. Ekrānuzņēmuma ID parasti nāk no
`local search-screen` vai SQL virs `screenshots` tabulas. Ja Desktop atgriež
strukturētu kļūdu, piem., `screenshot_pending`, `screenshot_file_missing` vai
`screenshot_chunk_corrupted`, JSON režīms saglabā `reason`, `hint` un
`screenshot_id` laukus stderr, lai aģenti varētu mēģināt ar vecāku ID vai
ziņot par precīzu bloķētāju. Pārbaudiet veiksmīgus izvades ar `file PATH`
pirms nododat tos redzes rīkiem.

## Izpētīts piemērs: Python aģenta cilpa

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

## Ātruma ierobežojumu pārvaldība

Atmiņas: 120/st. Sarunas: 25/st. Partiju izveides: 15/st.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Padomi

* Izmantojiet `--profile <name>`, ja jūsu aģents pārvalda vairākas Omi kontus.
  Katram profilam ir savi akreditācijas dati un API bāze.
* Izmantojiet `--api-base http://localhost:8080` vietējiem backend testiem.
* Izmantojiet `OMI_LOCAL_API_URL` un `OMI_LOCAL_TOKEN`, lai aizstātu profila
  vietējās Desktop API iestatījumus vienai izpildei.
* Izmantojiet `--verbose` atkļūdošanai — tas reģistrē `METHOD path → status (Ns)`
  uz stderr, neietekmējot stdout, tāpēc JSON režīms paliek derīgs.
* Lai novirzītu saturu sarunā, izmantojiet `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
