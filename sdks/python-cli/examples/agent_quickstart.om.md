# omi-cli akka xidirtataa

> Gidduu golaattoota LLM (Claude Code, Cursor, botota kee) qopheessitaniif gorsa.

## Koomi CLI-n xidirtaatawiin lafilama

* **Wanti JSON gaggeeffama.** `--json` gara stdout JSON sirrii badhaa, fi
  *JSON* qofa — odeeffannoo butti, jijjiirama mootummaa hin jiru. Dogoggora
  gara stderr `{"error": "...", "detail": "..."}`.
* **Fuula badee gaggeeffama.** `0` milkaa'ina / `1` ittiin fayyadamuu / `2`
  adda baasuu / `3` sarvaraa / `4` deebii gadhiiti / `5` hin arganne.
  Golaattoota haarawa maaloo-alaala sagalee dubbisaa garagalchuu hin
  qabu.
* **Waliin gorsa biyyee tokko keessatti gahee hin jiru.** Adda faarsuu
  (toonni-yaada) ifaa; `--api-key` akka eegessa balleessituu yookaan
  `OMI_API_KEY` jalqabaa galiinsa gahee ittiin gadhiisi.
* **Deebii aanaan raga.** `429` fi `5xx` duraan deebii gadii jechootan
  itti fayyadamuu of tuffachuu.

## Adda baasuu (lameen, namattiin)

Maamiltoon app web Omi irraa (`https://app.omi.me` → Developer → API Keys)
jaalala API gargaarsaa barreessituu fi kana:

```bash
omi auth login                          # gaali biyyee; jaalala meeshaa kee
                                         # seenaa irratti hin mul'atu
# yookaan
export OMI_API_KEY=omi_dev_...          # yeroo dura, konteenaraaf mijaa
```

## Golaattootni baay'ee garaagarummaa murrattiini

### 1. Yaadannoo dubbisi

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Yaadannoo uumi

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Haasawa dubbisi

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Hojii banuu dubbisi

```bash
omi action-item list --json --open
```

### 5. Hojii xumurame akka dubbisii

```bash
omi action-item complete --json a1b2c3d4
```

## API Gosa Desktop

Omi Desktop API isaa gosa jireenya banamee dha, golaattoota karaa dabaluun
seenaa meeshaa, gabaabii, SQL fi ajaja barreessuu ni danda'u
(hojii API gargaarsaa jireenya dursa hin fayyadamuu):

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# yookaan, yeroo gadii aanaa:
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

Golaattoon barreessuu tingaa xumura yookaan haqi namoonni galmeessuu
dhiisaa yeroo fayyadamtoon ni gaafata:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` suurseenii fayilitti
gala fi skiriiptiif stdout irratti JSON deebisuun ni tiyya. Suurseenii ID
`local search-screen` yookaan SQL `screenshots` gabatee irratti akka
barreessituu ni tilmaama. Desktop dogoggora sirrii kennaaniin akka
`screenshot_pending`, `screenshot_file_missing`, yookaan
`screenshot_chunk_corrupted` deebisu, JSON moodi `reason`, `hint`, fi
`screenshot_id` qabuu stderritti ni kaa'u tti golaattoon ID garaagara
deebisu yookaan cabsii xiqqa barreessuu ni danda'u. Kunya mijaan
`file PATH` ibsuun haa seenin sadaqaa oomishaan dura.
 
## Fakkeenya: golaattoon Python loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI JSON moodiiti waamii, fuula badee ittiin aa'iitti."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON moodiitti dogoggora sirrii stderritti barreessa:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Hojii banuu hunda dubbisi fi kennaaniin guutuu 30 maattiin gadi qabii.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gadii fayyadamuu eeguu

Yaadannoo: 120/awaattii. Haasawa: 25/awaattii. Uumamaa paakaa: 15/awaattii.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # deebii gadhiitee
    err = json.loads(result.stderr)
    # err["detail"] akka "Retry in 12s. ..." ni dursa
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Gorsa

* `--profile <maqaa>` fayyadamaa yoo golaattoon kee iddoo Omi hundaa
  turee. Wanti tokko galmee ofii fi karaa API isaa qabatu.
* `--api-base http://localhost:8080` backend gosa jireenya buuxuuf.
* `OMI_LOCAL_API_URL` fi `OMI_LOCAL_TOKEN` garaara karaa API Desktop
  bakka bisi yeroo tokkoof.
* `--verbose` agarfee dogoggorruf — `METHOD path → status (Ns)` stderritti
  barreessa, stdout hin buusin, JSON moodi ni miilaa.
* Qabiyyee haasawaotti haandii melliisuu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
