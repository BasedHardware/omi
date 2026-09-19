# omi-cli AI agenteentzat

> LLM bidez gidatutako sistemetarako gida praktikoa (Claude Code, Cursor, zure bot pertsonalizatuak).

## Zergatik den CLIa agenteentzat erraza

* **JSON kontratu egonkorra.** `--json` banderak baliozko JSON dokumentu bat igortzen du stdout-era
  eta *soilik* JSON dokumentu bat — aurrerapen mezurik eta kargatze-animaziorik gabe. Akatsak
  stderr-era bidaltzen dira `{"error": "...", "detail": "..."}` formatuan.
* **Irteera-kode egonkorrak.** `0` ados / `1` erabilera okerra / `2` autentifikazioa / `3` zerbitzaria /
  `4` eskaera-muga gainditua / `5` ez da aurkitu. Agenteak kode hauetan oinarrituta adar daitezke
  hizkuntza naturaleko akatsak aztertu beharrik gabe.
* **Eskaera interaktiborik ez headless testuinguruetan.** Pasatu `--yes` (edo `-y`) komando
  suntsitzaileetarako; pasatu `--api-key` edo ezarri `OMI_API_KEY` saio-hasiera interaktiboa saltatzeko.
* **Barkabera den birsaiaketa-portaera.** `429` eta `5xx` akatsak automatikoki birsaiatzen dira
  atzera-egite esponentzialarekin (backoff) jakinarazi aurretik.

## Autentifikazioa (behin bakarrik, gizakiak egina)

Erabiltzaileak garatzailearen API gakoa lortzen du Omi web aplikaziotik
(`https://app.omi.me` → Developer → API Keys) eta hauetako bat egiten du:

```bash
omi auth login                          # itsaste interaktiboa; gakoa ez da shell-eko historian gordetzen
# edo
export OMI_API_KEY=omi_dev_...          # behin-behinekoa, edukiontzietarako egokia
```

## Agenteek gehien egiten dituzten bost ekintzak

### 1. Memoriak irakurri

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Memoria sortu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Elkarrizketak irakurri

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Irekitako ekintza-elementuak irakurri

```bash
omi action-item list --json --open
```

### 5. Ekintza-elementua eginda bezala markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Tokiko Desktop APIa

Omi Desktop-ek bere tokiko APIa gaitzen duenean, agenteek gailuko pantaila-historia, laburpenak,
SQL datuak eta zereginak kontsulta ditzakete hodeiko dev APIa erabili gabe:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# edo behin-behineko saioetarako:
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

Zereginak osatu edo ezabatu erabiltzaileak berariaz eskatzen duenean bakarrik:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` komandoak pantaila-argazkia diskoan gordetzen
du eta JSON igortzen jarraitzen du stdout-era script-etarako. Pantaila-argazkiaren IDa normalean
`local search-screen` komandotik edo `screenshots` taulako SQL kontsultatik lortzen da. Desktop-ek
akats egituratu bat itzultzen badu (hala nola `screenshot_pending`, `screenshot_file_missing`
edo `screenshot_chunk_corrupted`), JSON moduak `reason`, `hint` eta `screenshot_id` eremuak
gordetzen ditu stderr-en, agenteek ID zaharrago bat probatu ahal izateko edo oztopo zehatza
jakinarazteko. Egiaztatu irteera arrakastatsuak `file PATH` erabiliz ikusmen-tresnetara bidali aurretik.

## Adibide praktikoa: Python agente-begizta

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

## Eskaera-mugak kudeatzea (Rate Limits)

Memoriak: 120/orduko. Elkarrizketak: 25/orduko. Multzo-sorkuntzak: 15/orduko.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <name>` zure agenteak Omi kontu bat baino gehiago kudeatzen baditu. Profil
  bakoitzak bere kredentzialak eta API oinarria ditu.
* Erabili `--api-base http://localhost:8080` tokiko backend-a probatzeko.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` ingurune-aldagaiak profilaren tokiko
  Desktop API ezarpenak baliogabetzeko exekuzio bakarrerako.
* Erabili `--verbose` arazketarako — `METHOD path → status (Ns)` erregistratzen du stderr-en
  stdout-i eragin gabe, JSON moduak baliozkoa izaten jarrai dezan.
* Edukia elkarrizketa batera bideratzeko, erabili `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
