# omi-cli agenteentzat (Euskara)

> LLM bidezko sistemetarako (Claude Code, Cursor, zure bot pertsonalak) gida praktikoa.

## Zergatik den CLI hau egokia agenteentzat

* **JSON kontratu egonkorra.** `--json` aukerak baliozko JSON dokumentu bat soilik igortzen du stdout bidez — aurrerapen-mezurik gabe eta birakari (spinner) gabe. Akatsak stderr bidez bidaltzen dira honako formatu honekin: `{"error": "...", "detail": "..."}`.
* **Irteera-kode egonkorrak.** `0` ados / `1` erabilera-akatsa / `2` autentifikazioa / `3` zerbitzaria / `4` abiadura-muga (rate limited) / `5` ez da aurkitu. Agenteek kode horien arabera egin ditzakete adarkatzeak, hizkuntza naturaleko mezuak analizatu beharrik gabe.
* **Galdetegi interaktiborik ez headless testuinguruetan.** Pasatu `--yes` (edo `-y`) ekintza suntsitzaileei; pasatu `--api-key` edo ezarri `OMI_API_KEY` saio-hasiera interaktiboa saihesteko.
* **Birkonexio eta saiakera automatiko toleranteak.** `429` eta `5xx` erroreak atzerapen esponentzialarekin berriro saiatzen dira erabiltzaileari errore gisa bistaratu aurretik.

## Autentifikazioa (behin bakarrik, gizakiak egina)

Erabiltzaileak garatzailearen API gakoa eskuratzen du Omi web aplikazioan (`https://app.omi.me` → Developer → API Keys) eta honela konfiguratzen du:

```bash
omi auth login                          # itsaste interaktiboa; gakoa ez da shell historian gordetzen
# edo
export OMI_API_KEY=omi_dev_...          # behin-behinekoa, edukiontzietarako (Docker) aproposa
```

## Agenteek gehien egiten dituzten bost gauzak

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

### 4. Irekitako ekintza-elementuak irakurri

```bash
omi action-item list --json --open
```

### 5. Ekintza-elementu bat amaitutzat markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Tokiko Mahaigaineko APIa (Local Desktop API)

Omi Desktop aplikazioak bere tokiko APIa gaitzen duenean, agenteek gailuko pantaila-historia, laburpenak, SQL eta atazak kontsulta ditzakete hodeiko dev APIa erabili gabe:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# edo, behin-behineko saioetarako:
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

Amaitu edo ezabatu atazak soilik erabiltzaileak esplizituki eskatzen duenean:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` aginduak pantaila-argazkia diskoan gordetzen du eta JSON formatua bistaratzen du stdout bidez script-etarako. Pantaila-argazkiaren IDa `local search-screen` bidez edo `screenshots` taularen gaineko SQL kontsulten bidez lortu ohi da. Desktop-ek akats egituratu bat itzultzen badu (adibidez, `screenshot_pending`, `screenshot_file_missing` edo `screenshot_chunk_corrupted`), JSON moduak `reason`, `hint` eta `screenshot_id` eremuak gordetzen ditu stderr bidez, agenteek aurreko ID batekin berriro saiatu edo blokeo zehatza jakinarazi ahal izateko. Balioztatu irteera arrakastatsuak `file PATH` bidez ikusmen-tresnetara (vision tools) bidali aurretik.

## Adibide osoa: Python agentearen begizta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Deitu omi CLI tresnari JSON moduan, errore-kodeetan salbuespena sortuz."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLIak errore egituratuak idazten ditu stderr-en JSON moduan:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi errorearekin amaitu da {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Irekitako ekintza-elementu guztiak irakurri eta 30 egun baino gehiago dituztenak amaitutzat markatu.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Abiadura-mugak kudeatzea (Rate Limits)

Oroitzapenak: 120/orduko. Elkarrizketak: 25/orduko. Sortze bateratuak (batch creates): 15/orduko.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # abiadura-muga gainditua
    err = json.loads(result.stderr)
    # err["detail"] itxura honakoa da: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <izena>` zure agenteak Omi kontu anitz kudeatzen baditu. Profil bakoitzak bere kredentzialak eta oinarrizko API helbidea ditu.
* Erabili `--api-base http://localhost:8080` tokiko backend-ak probatzeko.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` exekuzio baterako profil-tokiko Mahaigaineko API ezarpenak gainidazteko.
* Erabili `--verbose` arazketarako — `METHOD bidea → egoera (Ns)` erregistratzen du stderr bidez stdout kaltetu gabe, JSON moduak baliozkoa izaten jarrai dezan.
* Edukia elkarrizketa batera bideratzeko (piping), erabili `--text -`:
  ```bash
  cat bilera_oharrak.md | omi conversation create --text - --text-source other_text
  ```
