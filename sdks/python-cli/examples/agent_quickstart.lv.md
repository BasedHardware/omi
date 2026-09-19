# omi-cli aģentiem

> Praktisks ceļvedis LLM vadītām vidēm (Claude Code, Cursor, jūsu pielāgotajiem botiem).

## Kāpēc CLI ir piemērots aģentiem

* **Stabils JSON līgums.** Parametrs `--json` uz stdout izvada derīgu JSON dokumentu un *tikai* JSON dokumentu — bez progresa ziņojumiem vai ielādes indikatoriem. Kļūdas tiek novirzītas uz stderr kā `{"error": "...", "detail": "..."}`.
* **Stabili izejas kodi.** `0` veiksmīgi / `1` lietošanas kļūda / `2` autentifikācija / `3` serveris / `4` ātruma ierobežojums / `5` nav atrasts. Aģenti var pieņemt lēmumus pēc šiem kodiem, neparsējot kļūdas dabiskajā valodā.
* **Nav interaktīvu vaicājumu bezgalvas (headless) vidē.** Destruktīvām komandām pievienojiet `--yes` (vai `-y`); norādiet `--api-key` vai iestatiet `OMI_API_KEY`, lai izlaistu interaktīvo pieteikšanos.
* **Iecietīga atkārtošanas loģika.** Kļūdas `429` un `5xx` tiek automātiski atkārtotas ar eksponenciālu atkāpšanos pirms to izvadīšanas.

## Autentifikācija (vienreizēja, veic cilvēks)

Lietotājs iegūst izstrādātāja API atslēgu Omi tīmekļa lietotnē (`https://app.omi.me` → Developer → API Keys) un veic vienu no darbībām:

```bash
omi auth login                          # interaktīva ielīmēšana; atslēga nepaliek čaulas vēsturē
# vai
export OMI_API_KEY=omi_dev_...          # īslaicīgs, ērts konteineros
```

## Piecas darbības, ko aģenti veic visbiežāk

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

### 4. Lasīt atvērtos uzdevumus

```bash
omi action-item list --json --open
```

### 5. Atzīmēt uzdevumu kā pabeigtu

```bash
omi action-item complete --json a1b2c3d4
```

## Lokālais Desktop API

Kad Omi Desktop atver savu lokālo API, aģenti var vaicāt ierīces ekrāna vēsturi, kopsavilkumus, SQL un uzdevumus, neizmantojot mākoņa izstrādātāja API:

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

Pabeidziet vai dzēsiet uzdevumus tikai tad, kad lietotājs to skaidri pieprasa:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` saglabā ekrānuzņēmumu diskā un skriptiem joprojām izvada JSON uz stdout. Ekrānuzņēmuma ID parasti iegūst no `local search-screen` vai SQL vaicājuma tabulā `screenshots`. Ja Desktop atgriež strukturētu kļūdu, piemēram, `screenshot_pending`, `screenshot_file_missing` vai `screenshot_chunk_corrupted`, JSON režīms saglabā laukus `reason`, `hint` un `screenshot_id` uz stderr, lai aģenti varētu mēģināt vecāku ID vai ziņot par konkrēto šķērsli. Pirms nodošanas vizuālajiem rīkiem apstipriniet faila derīgumu ar `file PATH`.

## Praktisks piemērs: Python aģenta cilpa

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Izsauc omi CLI JSON režīmā, izraisot izņēmumu pie neveiksmīgiem izejas kodiem."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON režīmā izvada strukturētas kļūdas uz stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi beidza darbu ar kodu {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Nolasa visus atvērtos uzdevumus un pabeidz tos, kas vecāki par 30 dienām.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Pieprasījumu ierobežojumu pārvaldība

Atmiņas: 120/stundā. Sarunas: 25/stundā. Masveida izveide: 15/stundā.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ātruma ierobežojums
    err = json.loads(result.stderr)
    # err["detail"] izskatās šādi: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Padomi

* Izmantojiet `--profile <nosaukums>`, ja jūsu aģents pārvalda vairākus Omi kontus. Katram profilam ir savi akreditācijas dati un API bāze.
* Izmantojiet `--api-base http://localhost:8080` lokālai aizmugursistēmas testēšanai.
* Izmantojiet `OMI_LOCAL_API_URL` un `OMI_LOCAL_TOKEN`, lai vienam izpildes ciklam ignorētu profila lokālos Desktop API iestatījumus.
* Izmantojiet `--verbose` atkļūdošanai — tas reģistrē `METHOD path → status (Ns)` uz stderr, neietekmējot stdout, saglabājot derīgu JSON režīmu.
* Satura ievadīšanai sarunā caur konveijeru (pipe) izmantojiet `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
