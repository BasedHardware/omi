# omi-cli agententzat

> LLM bidez gidatutako tresnetarako gida praktikoa (Claude Code, Cursor, zure bot propioak).

## Zergatik da CLI lagunkoia agententzat

* **JSON kontratu egonkorra.** `--json` baliozko JSON dokumentu bat igortzen du stdout-era eta
  *soilik* JSON dokumentu bat — ez progresu-mezurik, ez spinnerrik. Erroreak stderr-era joaten dira
  `{"error": "...", "detail": "..."}` gisa.
* **Irteera-kode egonkorrak.** `0` ondo / `1` erabilera / `2` autentifikazioa / `3` zerbitzaria / `4`
  tasa-muga / `5` ez da aurkitu. Agentek hauen arabera adarkatu dezakete, erroreak lengoaia
  naturalean analizatu gabe.
* **Ez dago eskaera interaktiborik testuinguru headless-etan.** Pasatu `--yes` (edo `-y`)
  komando suntsitzaileei; pasatu `--api-key` edo ezarri `OMI_API_KEY` saio-hasiera
  interaktiboa saihesteko.
* **Berriz saiatzeko jokabide malgua.** `429` eta `5xx` atzerapenarekin berriz saiatzen dira
  azaleratu aurretik.

## Autentifikazioa (behin, giza erabiltzaileak)

Erabiltzaileak garatzaile API gako bat lortzen du Omi web aplikaziotik
(`https://app.omi.me` → Developer → API Keys) eta gero:

```bash
omi auth login                          # itsatsi interaktiboa; gakoa ez da shell historialean geratzen
# edo
export OMI_API_KEY=omi_dev_...          # iragankorra, edukiontzietarako egokia
```

## Agentek gehien egiten dituzten bost gauzak

### 1. Memoriak irakurri

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Memoria bat sortu

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

### 5. Ekintza-elementu bat egindako gisa markatu

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API lokala

Omi Desktop-ek bere API lokala erakusten duenean, agentek gailuko pantaila-historia,
laburpenak, SQL eta zereginak kontsulta ditzakete hodeiko garatzaile APIa erabili gabe:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# edo, saio iragankorretarako:
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

Zereginak soilik osatu edo ezabatu erabiltzaileak argi eta garbi eskatzen duenean:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` pantaila-argazkia diskoan idazten du
eta oraindik JSON inprimatzen du stdout-era scriptentzat. Argazkiaren IDa normalean
`local search-screen`-tik edo `screenshots` taularen gaineko SQL-tik dator. Desktop-ek
`screenshot_pending`, `screenshot_file_missing` edo `screenshot_chunk_corrupted` bezalako
akats egituratu bat itzultzen badu, JSON moduak `reason`, `hint` eta `screenshot_id`
eremuak gordetzen ditu stderr-en, agentek ID zaharrago bat berriz saia dezaten edo
blokeo zehatza jakinaraz dezaten. Balioztatu irteera arrakastatsuak `file PATH`-rekin
ikusmen-tresnei pasatu aurretik.

## Adibide praktikoa: Python agente-begizta

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Deitu omi CLIari JSON moduan, arrakastatsuak ez diren irteera-kodeekin salbuespena jaurtiz."""
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
        raise RuntimeError(f"omi-k {result.returncode} irten du: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Irakurri ekintza-elementu ireki guztiak eta 30 egun baino zaharragoak egindako gisa markatu.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tasa-mugen kudeaketa

Memoriak: 120/ordu. Elkarrizketak: 25/ordu. Sortze-sorta: 15/ordu.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # tasa-muga
    err = json.loads(result.stderr)
    # err["detail"] antzekoa da: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Aholkuak

* Erabili `--profile <name>` zure agentek Omi kontu bat baino gehiago kudeatzen baditu.
  Profil bakoitzak bere kredentzialak eta API oinarria ditu.
* Erabili `--api-base http://localhost:8080` backend proba lokaletarako.
* Erabili `OMI_LOCAL_API_URL` eta `OMI_LOCAL_TOKEN` exekuzio batean profil baten
  Desktop API ezarpen lokalak gainidazteko.
* Erabili `--verbose` arazketarako — `METHOD path → status (Ns)` erregistratzen du stderr-en
  stdout-i eragin gabe, beraz JSON modua baliozkoa izaten jarraitzen du.
* Edukia elkarrizketa batera bidaltzeko, erabili `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
