# omi-cli ji bo ajanan

> Rêbernameyeke pratîk ji bo harnessên LLM (Claude Code, Cursor, botên te yên xwe).

## Çima CLI ji bo ajanan dostane ye

* **Peymana JSON a aram.** `--json` tenê belgeyeke JSON a derbasdar li stdoutê
  derdixe — *tenê* belgeyeke JSON — tu peyamên pêşveçûnê, tu spinner tune. Xeletî
  diçin stderrê wek `{"error": "...", "detail": "..."}`.
* **Kodên derketinê yên aram.** `0` serkeftî / `1` bikaranîn / `2` rastandin /
  `3` server / `4` sînorê lezê / `5` nehat dîtin. Ajan dikarin bêyî analîzkirina
  xeletiyên zimanê xwezayî li ser van kodan şax bigirin.
* **Di çarçoveyên headless de tu pirsên înteraktîf tune.** Ji bo fermanên
  wêranker `--yes` (an `-y`) bidin; ji bo derbaskirina têketina înteraktîf
  `--api-key` bidin an `OMI_API_KEY` saz bikin.
* **Tevgereke dubarekirinê ya bexşîner.** `429` û `5xx` berî xuya bibin
  bi backoffê têne dubare kirin.

## Rastandin (carekê, ji aliyê mirovan)

Bikarhêner ji sepana webê ya Omi (`https://app.omi.me` → Developer → API Keys)
kilîta dev API distîne û yek ji van dike:

```bash
omi auth login                          # pêveka înteraktîf; kilît di dîroka shell de namîne
# an
export OMI_API_KEY=omi_dev_...          # demkî, ji bo konteynerê guncav
```

## Pênc tiştên ku ajan herî zêde dikin

### 1. Bîranînan bixwîne

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Bîranînekê çêbike

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Danûstandinan bixwîne

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Tiştên çalakiyê yên vekirî bixwîne

```bash
omi action-item list --json --open
```

### 5. Tiştekî çalakiyê wek qediyayî nîşan bike

```bash
omi action-item complete --json a1b2c3d4
```

## API ya Desktop a Herêmî

Dema ku Omi Desktop API ya xwe ya herêmî eşkere dike, ajan dikarin bêyî bikaranîna
API ya dev a ewrî dîroka ekranê ya li ser cîhazê, kurtebêj, SQL û peywiran
lêpirsîn bikin:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# an, ji bo danişînên demkî:
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

Tenê gava ku bikarhêner bi eşkereyî daxwaz dike peywiran qedînin an jêbirin:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` screenshotê li dîskê dinivîse û
hîn jî ji bo skrîptan JSON li stdoutê çap dike. ID ya screenshotê bi gelemperî ji
`local search-screen` an SQL ya li ser tabloya `screenshots` tê. Heke Desktop
têkçûneke avahîsazî wek `screenshot_pending`, `screenshot_file_missing` an
`screenshot_chunk_corrupted` vegerîne, moda JSON li stderrê zeviyên `reason`,
`hint` û `screenshot_id` diparêze da ku ajan bikarin ID ya kevn dîsa biceribînin
an astengiya rastîn ragihînin. Berî ku encamên serkeftî bidin amûrên dîtinê, bi
`file PATH` piştrast bikin.

## Nimûneya xebitî: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI di moda JSON de bang bike û li ser kodên derketinê yên neserkeftî îstîsna derxe."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI di moda JSON de xeletiyên avahîsazî li stderrê çap dike:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Hemî tiştên çalakiyê yên vekirî bixwîne û her tiştê ku ji 30 rojan kevintir e qediyayî nîşan bike.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Rêvebiriya sînorên lezê

Bîranîn: 120/hr. Danûstandin: 25/hr. Çêkirinên kom: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # sînorê lezê
    err = json.loads(result.stderr)
    # err["detail"] wisa xuya dike: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Şîret

* Heke ajana te gelek hesabên Omi bi rê ve dibe `--profile <name>` bikar bîne.
  Her profîl xwedî îtîmada xwe û bingeha API ye.
* Ji bo testkirina backendê ya herêmî `--api-base http://localhost:8080` bikar bîne.
* Ji bo yek xebitandinê mîhengên Desktop API yên profîl-herêmî derbas bike
  `OMI_LOCAL_API_URL` û `OMI_LOCAL_TOKEN` bikar bîne.
* Ji bo debugkirinê `--verbose` bikar bîne — ew `METHOD path → status (Ns)` li stderrê
  tomar dike bêyî ku bandorê li stdout bike, lewma moda JSON derbasdar dimîne.
* Ji bo ku naverokê bi pipeyê têxe danûstandinê, `--text -` bikar bîne:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
