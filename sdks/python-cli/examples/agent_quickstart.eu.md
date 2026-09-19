# omi-cli agenteentzat

> Gida praktikoa LLM-k gidatutako tresnentzat (Claude Code, Cursor, zure bot propioak).

## Zergatik den CLI hau egokia agenteentzat

* **JSON kontratu egonkorra.** `--json` parametroak baliozko JSON dokumentu bat bidaltzen du stdout-era eta
  *bakarrik* JSON dokumentu bat — aurrerapen-mezurik edo animaziorik gabe. Akatsak
  stderr-era bidaltzen dira `{"error": "...", "detail": "..."}` moduan.
* **Irteera-kode egonkorrak.** `0` ongi / `1` erabilera-akatsa / `2` autentifikazioa / `3` zerbitzari-akatsa / `4` tasa-muga / `5` ez da aurkitu. Agenteek kode hauen arabera bideratu dezakete logika errore-mezuak analizatu beharrik gabe.
* **Gidalerro interaktiborik ez burugabeko testuinguruetan.** Erabili `--yes` (edo `-y`)
  agindu suntsitzaileetarako; erabili `--api-key` edo konfiguratu `OMI_API_KEY` saio-hasiera interaktiboa saltatzeko.
* **Barkabera den birsaiatze portaera.** `429` eta `5xx` erroreak atzerapenarekin berriro
  saiatzen dira errorea bistaratu aurretik.

## Autentifikazioa (behin bakarrik, gizakiak egina)

Erabiltzaileak garatzailearen API gakoa lortzen du Omi web aplikaziotik
(`https://app.omi.me` → Developer → API Keys) eta hauetako bat hautatzen du:

```bash
omi auth login                          # itsatsi interaktiboa; gakoa ez da terminaleko historian gordetzen
# edo
export OMI_API_KEY=omi_dev_...          # behin-behinekoa, ontziekin bateragarria
```

## Agenteek gehien egiten dituzten bost gauzak

### 1. Memoriak irakurri

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Memoria bat sortu

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

### 5. Ekintza-elementu bat eginda bezala markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Tokiko Mahaigaineko APIa (Desktop API)

Omi Desktop-ek bere tokiko APIa eskuragarri jartzen duenean, agenteek gailuko pantaila-historia,
laburpenak, SQL eta zereginak kontsulta ditzakete hodeiko APIa erabili gabe:

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

Bete edo ezabatu zereginak erabiltzaileak berariaz eskatzen duenean bakarrik:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` aginduak pantaila-argazkia diskoan
idazten du eta JSON stdout-era bidaltzen jarraitzen du scriptek erabil dezaten. Pantaila-argazkiaren IDa
normalean `local search-screen` komandotik edo `screenshots` taularen gaineko SQL kontsultatik dator.
Desktop-ek egituratutako akats bat itzultzen badu (adibidez, `screenshot_pending`, `screenshot_file_missing`
edo `screenshot_chunk_corrupted`), JSON moduak `reason`, `hint` eta `screenshot_id` eremuak
gordetzen ditu stderr-en, agenteek ID zaharrago batekin berriro saiatzeko edo oztopo zehatza
jakinarazteko aukera izan dezaten. Egiaztatu emaitzak `file PATH` erabiliz ikusmen-ereduei bidali aurretik.

## Adibide osoa: Python agente-begizta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Deitu omi CLIari JSON moduan, salbuespen bat jaurtiz errore-kodeetan."""
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
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Irakurri irekitako ekintza guztiak eta markatu 30 egun baino zaharragoak eginda gisa.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tasa-mugak kudeatzea (rate limits)

Memoriak: 120/orduko. Elkarrizketak: 25/orduko. Multzoko sorrerak: 15/orduko.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # tasa-muga gainditua
    err = json.loads(result.stderr)
    # err["detail"] honelakoa da: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <izena>` zure agenteak Omi kontu anitz kudeatzen baditu. Profil
  bakoitzak bere egiaztagiriak eta API oinarria ditu.
* Erabili `--api-base http://localhost:8080` tokiko probak egiteko.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` profilaren tokiko Desktop API ezarpenak
  gainidazteko exekuzio bakar baterako.
* Erabili `--verbose` arazketarako — `METHOD path → status (Ns)` erregistratzen du stderr-en
  stdout-i eragin gabe, beraz JSON moduak baliozkoa izaten jarraitzen du.
* Edukia elkarrizketa batera kanalizatzeko (pipe), erabili `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
