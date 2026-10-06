# omi-cli agenteentzat

> LLM bidezko inguruneetarako gida praktikoa (Claude Code, Cursor edo zure bot propioak).

## Zergatik den CLIa egokia agenteentzat

* **JSON kontratu egonkorra.** `--json` aukerak baliozko JSON dokumentu bat igortzen du stdout-en eta *JSON dokumentu bat bakarrik*: ez du aurrerapen mezurik ezta biraketarik erakusten. Erroreak stderr-era doaz `{"error": "...", "detail": "..."}` formatuan.
* **Irteera kode egonkorrak.** `0` ados / `1` erabilera okerra / `2` autentifikazioa / `3` zerbitzaria / `4` eskaera muga / `5` ez da aurkitu. Agenteek kode horien arabera har ditzakete erabakiak, hizkuntza naturaleko erroreak aztertu beharrik gabe.
* **Gonbita interaktiborik ez headless testuinguruetan.** Pasatu `--yes` (edo `-y`) komando suntsitzaileei; pasatu `--api-key` edo ezarri `OMI_API_KEY` saio-hasiera interaktiboa saltatzeko.
* **Berrezarpen tolerantea.** `429` eta `5xx` erroreak atzerapenarekin berrezartzen dira erabiltzaileari itzuli aurretik.

## Autentifikazioa (behin bakarrik, erabiltzaileak egina)

Erabiltzaileak garatzaileentzako API gako bat lortzen du Omi web aplikaziotik (`https://app.omi.me` → Developer → API Keys) eta aukera hauetako bat erabiltzen du:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Agenteek gehien egiten dituzten bost zereginak

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

### 4. Egiteke dauden zereginak irakurri

```bash
omi action-item list --json --open
```

### 5. Zeregin bat eginda bezala markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Tokiko Desktop APIa

Omi Desktopek bere tokiko APIa gaitzen duenean, agenteek gailuko pantaila-historia, laburpenak, SQL eta zereginak kontsulta ditzakete hodeiko garatzaile APIa erabili gabe:

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

Osatu edo ezabatu zereginak erabiltzaileak argi eta garbi eskatzen duenean bakarrik:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` argazkia diskoan idazten du eta oraindik JSON inprimatzen du stdout-en scriptetarako. Argazkiaren IDa `local search-screen` edo `screenshots` taularen gaineko SQLtik etorri ohi da. Desktopek hutsegite egituratu bat itzultzen badu (adibidez, `screenshot_pending`, `screenshot_file_missing` edo `screenshot_chunk_corrupted`), JSON moduak `reason`, `hint` eta `screenshot_id` eremuak gordetzen ditu stderr-en, agenteak aurreko ID batekin berriro saiatu edo oztopo zehatzaren berri eman ahal izateko. Baliozkotu irteera arrakastatsuak `file PATH` erabiliz ikusmen-tresnetara pasa aurretik.

## Adibide osoa: Python agentearen zikloa

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

## Eskaera-mugak nola kudeatu

Oroitzapenak: 120 orduko. Elkarrizketak: 25 orduko. Multzoko sorrerak: 15 orduko.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <izena>` zure agenteak Omi kontu anitz kudeatzen baditu. Profil bakoitzak bere kredentzialak eta API oinarria ditu.
* Erabili `--api-base http://localhost:8080` tokiko backend-a probatzeko.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` exekuzio bakarrean profilaren tokiko Desktop API ezarpenak gainidazteko.
* Erabili `--verbose` arazteko — `METHOD path → status (Ns)` erregistratzen du stderr-en stdout aldatu gabe, beraz JSON moduak baliozkoa izaten jarraitzen du.
* Edukia elkarrizketa batera bideratzeko, erabili `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
