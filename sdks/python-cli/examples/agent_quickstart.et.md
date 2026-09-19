# omi-cli AI-agentidele

> Praktiline juhend LLM-põhistele süsteemidele (Claude Code, Cursor, kohandatud robotid).

## Miks CLI on agendisõbralik

* **Stabiilne JSON leping.** Lipp `--json` väljastab kehtiva JSON-dokumendi stdout-i ja
  *ainult* JSON-dokumendi — ilma edenemisteadete ja laadimisikoonideta. Vead suunatakse
  stderr-i vormingus `{"error": "...", "detail": "..."}`.
* **Stabiilsed väljumiskoodid.** `0` korras / `1` kasutusviga / `2` autentimine / `3` serveri viga /
  `4` päringulimiit ületatud / `5` ei leitud. Agendid saavad nende koodide põhjal otse hargneda
  ilma loomulikus keeles veateadete parsimiseta.
* **Puuduvad interaktiivsed viibad headless keskkonnas.** Edastage hävitavate käskude korral `--yes`
  (või `-y`); interaktiivse sisselogimise vahelejätmiseks edastage `--api-key` või määrake `OMI_API_KEY`.
* **Vabandav korduskatsete käitumine.** Vigade `429` ja `5xx` korral tehakse enne veast teatamist
  automaatselt uusi katseid eksponentsiaalse tagasitõmbumisega (backoff).

## Autentimine (ühekordne, inimese poolt)

Kasutaja hangib arendaja API-võtme Omi veebirakendusest
(`https://app.omi.me` → Developer → API Keys) ja teeb ühe järgmistest:

```bash
omi auth login                          # interaktiivne kleepimine; võtit ei salvestata shelli ajalukku
# või
export OMI_API_KEY=omi_dev_...          # ajutine, konteinerisõbralik
```

## Viis toimingut, mida agendid teevad kõige sagedamini

### 1. Mälestuste lugemine

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Mälestuse loomine

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Vestluste lugemine

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Avatud tegevusüksuste lugemine

```bash
omi action-item list --json --open
```

### 5. Tegevusüksuse märkimine tehtuks

```bash
omi action-item complete --json a1b2c3d4
```

## Kohalik Desktop API

Kui Omi Desktop avab oma kohaliku API, saavad agendid pärida seadme ekraaniajalugu,
kokkuvõtteid, SQL-andmeid ja ülesandeid ilma pilve dev-API-t kasutamata:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# või ajutiste seansside jaoks:
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

Lõpetage või kustutage ülesandeid ainult siis, kui kasutaja seda selgelt palub:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Käsk `omi local screenshot SCREENSHOT_ID --output PATH` salvestab ekraanipildi kettale
ja väljastab skriptide jaoks stdout-i endiselt JSON-i. Ekraanipildi ID pärineb tavaliselt
käsust `local search-screen` või SQL-päringust tabelist `screenshots`. Kui Desktop tagastab
struktureeritud tõrke, näiteks `screenshot_pending`, `screenshot_file_missing` või
`screenshot_chunk_corrupted`, säilitab JSON-režiim väljad `reason`, `hint` ja `screenshot_id`
stderr-is, et agendid saaksid proovida vanemat ID-d või teatada täpsest takistusest.
Enne väljundite edastamist nägemistööriistadele (vision tools) kontrollige neid käsuga `file PATH`.

## Praktiline näide: Pythoni agenditsükkel

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

## Päringupiirangute haldamine (Rate Limits)

Mälestused: 120/tund. Vestlused: 25/tund. Hulgiloomised: 15/tund.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Näpunäited

* Kasutage `--profile <name>`, kui teie agent haldab mitut Omi kontot. Igal
  profiilil on oma mandaadid ja API baasaadress.
* Kasutage `--api-base http://localhost:8080` kohaliku tagasüsteemi testimiseks.
* Kasutage keskkonnamuutujaid `OMI_LOCAL_API_URL` ja `OMI_LOCAL_TOKEN`, et tühistada
  profiili kohalikud Desktop API sätted üheks käivituseks.
* Silumiseks kasutage lippu `--verbose` — see logib `METHOD path → status (Ns)` stderr-i
  ilma stdout-i mõjutamata, nii et JSON-režiim jääb kehtima.
* Sisu suunamiseks vestlusse kasutage `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
