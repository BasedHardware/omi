# omi-cli agenteentzat

> LLM bidez gidatutako harnessentzako gida praktikoa (Claude Code, Cursor, zure bot propioak).

## Zergatik da CLIa agenteentzat egokia

* **JSON kontratu egonkorra.** `--json`-k JSON dokumentu baliozko bat igortzen du
  stdout-era eta *bakarrik* JSON dokumentu bat — ez aurrerapen-mezurik, ez spinner-rik.
  Erroreak stderr-era doaz `{"error": "...", "detail": "..."}` gisan.
* **Irteera-kode egonkorrak.** `0` ondo / `1` erabilera / `2` auth / `3` zerbitzaria /
  `4` tasa-muga / `5` ez da aurkitu. Agenteei haiekin adar ezin diezaiekete hizkuntz
  arrunteko erroreak parseatu gabe.
* **Ez prompt interaktiborik headless testuinguruetan.** `--yes` (edo `-y`) pasatu
  komando suntsitzaileei; `--api-key` edo `OMI_API_KEY` ezarri login interaktiboa
  saltatzeko.
* **Berriz saiakera portaera barkatzailea.** `429` eta `5xx` backoff-ekin
  berriz saiatzen dira agertu aurretik.

## Auth (behin, gizakiak)

Erabiltzaileak dev API giltza bat lortzen du Omi web-aplika­tiotik
(`https://app.omi.me` → Developer → API Keys) eta ondokoetakoren bat:

```bash
omi auth login                          # interaktiboa itsasteko; giltza ez da shell-historian gordetzen
# edo
export OMI_API_KEY=omi_dev_...          # laburra, kontainerrarentzat egokia
```

## Agenteei gehien egiten dieten bost gauza

### 1. Oroitzapenak irakurri

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Oroitzapen bat sortu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Elkarrizketak irakurri

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Irekitako ekintza-puntuak irakurri

```bash
omi action-item list --json --open
```

### 5. Ekintza-puntu bat egindako gisa markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Mahaigaineko API lokala

Omi Desktop-k bere API lokala erakusten duenean, agenteek gailuko
pantaila-historia, laburpenak, SQL eta atazak kontsulta ditzakete hodeiko dev APIa
erabili gabe:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# edo, aldi baterako saioetarako:
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

Atazak bakarrik osatu edo ezabatu erabiltzaileak argi eskatzen duenean:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH`-k pantaila-argazkia diskoan
idazten du eta oraindik JSONa inprimatzen du stdout-en scriptentzat. Pantaila-IDa
normalean `local search-screen`-etik edo `screenshots` taularen SQL-etik dator.
Desktop-ek `screenshot_pending`, `screenshot_file_missing` edo
`screenshot_chunk_corrupted` bezalako errore egituratua itzultzen badu,
JSON moduak `reason`, `hint` eta `screenshot_id` eremuak gordetzen ditu stderr-en
agenteek ID zaharrago bat berriz saiatzeko edo blokeatzaile zehatza jakinarazteko.
Balioztatu emaitza onak `file PATH`-rekin vision-tresnei pasatu aurretik.

## Adibide landua: Python agente begizta

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

## Tasa-mugen kudeaketa

Oroitzapenak: 120/or. Elkarrizketak: 25/or. Loteka sortzeak: 15/or.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <name>` zure agenteak hainbat Omi kontu kudeatzen baditu.
  Profil bakoitzak bere kredentzialak eta API oinarria ditu.
* Erabili `--api-base http://localhost:8080` backend lokaleko probetarako.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` profil-lokaleko
  Desktop API ezarpenak saihetseko exekuzio bakar baterako.
* Erabili `--verbose` arazketa egiteko — `METHOD path → status (Ns)` erregistratzen
  du stderr-en stdout-a eragin gabe, beraz JSON modua baliozkoa izaten jarraitzen du.
* Elkarrerizketa batera edukia pipe-tzeko, erabili `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
