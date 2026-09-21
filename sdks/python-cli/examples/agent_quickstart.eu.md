# omi-cli agententzat

> Gida praktikoa LLM bidezko harnesientzat (Claude Code, Cursor, zure bot propioak).

## Zergatik da CLI agente-lagungarria

* **JSON kontratu egonkorra.** `--json` erabiltzean stdout-era JSON dokumentu baliogarri
  bat igortzen du eta *bakarrik* JSON dokumentu bat — ez aurrerapen-mezurik, ez
  biragailuerik. Erroreak stderr-era doaz `{"error": "...", "detail": "..."}` moduan.
* **Irteera-kode egonkorrak.** `0` ondo / `1` erabilera / `2` autentifikazioa / `3`
  zerbitzaria / `4` abiadura mugatua / `5` ez da aurkitu. Agenteek hauen arabera
  adarratu dezakete hizkuntza naturaleko erroreak parseatu gabe.
* **Ez dago elkarrizketa-eskaera interaktiborik testuinguru burugebeetan.** Pasa
  `--yes` (edo `-y`) komando suntsitzaileetan; pasa `--api-key` edo ezarri
  `OMI_API_KEY` saio-hasiera interaktiboa saltatzeko.
* **Berrespen-portaera barkabera.** `429` eta `5xx` atzerapen bidez berresten dira
  azaleratu aurretik.

## Autentifikazioa (behin, pertsonak egindakoa)

Erabiltzaileak garatzaileen API gako bat lortzen du Omi web aplikaziotik
(`https://app.omi.me` → Developer → API Keys) eta:

```bash
omi auth login                          # itsaspen interaktiboa; gakoa ez dago shell-aren historian
# edo
export OMI_API_KEY=omi_dev_...          # iraunkorra, edukiontzi-lagungarria
```

## Agenteek gehien egiten dituzten bost gauzak

### 1. Oroitzapenak irakurri

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Oroitzapen bat sortu

```bash
omi memory create --json "Erabiltzaileak modu iluna nahiago du" --category lifestyle
```

### 3. Elkarrizketak irakurri

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ekintza-elementu irekiak irakurri

```bash
omi action-item list --json --open
```

### 5. Ekintza-elementu bat egindakotzat markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Tokiko mahaigaineko APIa

Omi Desktop-ek bere tokiko APIa erakusten duenean, agenteek gailuko pantaila-historia,
laburpenak, SQL eta atazak kontsultatu ditzakete hodeiko garatzaileen APIa erabili gabe:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# edo, saio iraunkorretarako:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"prezio orrialdea","days":7}'
omi --json local search-screen "prezio orrialdea" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "zergak" --include-completed
```

Osatu edo ezabatu atazak erabiltzaileak argi eskatzen duenean bakarrik:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` komandoak pantaila-argazkia diskoan
idazten du eta JSON stdout-era inprimatzen jarraitzen du script-entzat. Pantaila-argazki
IDa normalean `local search-screen` edo `screenshots` taulako SQL-tik dator. Desktop-ek
porrot egituratua itzultzen badu, hala nola `screenshot_pending`,
`screenshot_file_missing` edo `screenshot_chunk_corrupted`, JSON moduak `reason`, `hint`
eta `screenshot_id` eremuak gordetzen ditu stderr-en, agenteek ID zaharrago bat berrerabil
dezaten edo blokeatzaile zehatza jakinaraz dezaten. Egiaztatu irteera arrakastatsuak
`file PATH` erabiliz ikusmen-tresnetara pasatu aurretik.

## Lan-adibidea: Python agenteen begizta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Deitu omi CLIa JSON moduan, arrakasta ez diren irteera-kodeetan errorea jaurtiz."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLIak errore egituratuak inprimatzen ditu stderr-era JSON moduan:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Irakurri ekintza-elementu ireki guztiak eta markatu 30 egun baino zaharragoak osatuta.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Abiadura-mugen kudeaketa

Oroitzapenak: 120/orduko. Elkarrizketak: 25/orduko. Sorrera masiboak: 15/orduko.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # abiadura mugatua
    err = json.loads(result.stderr)
    # err["detail"] honelakoa da: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <izena>` zure agenteak Omi kontu anitz kudeatzen baditu. Profil
  bakoitzak bere kredentzialak eta API oinarria ditu.
* Erabili `--api-base http://localhost:8080` tokiko backend probetarako.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` profilaren tokiko Desktop API
  ezarpenak exekuzio baterako gainidazteko.
* Erabili `--verbose` arazketetarako — `METHOD path → status (Ns)` erregistratzen du
  stderr-era stdout-a eragin gabe, JSON modua baliozko mantenduz.
* Edukia elkarrizketa batera bideratzeko, erabili `--text -`:
  ```bash
  cat bilera_oharrak.md | omi conversation create --text - --text-source other_text
  ```
