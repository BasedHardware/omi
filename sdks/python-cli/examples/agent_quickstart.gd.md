# omi-cli airson àidseantan

> Stiùireadh practaigeach airson acfhainn air a stiùireadh le LLM (Claude Code, Cursor, na botaichean agad fhèin).

## Carson a tha an CLI càirdeil dha àidseantan

* **Cùmhnant JSON seasmhach.** Sgaoileas `--json` sgrìobhainn JSON dhligheach gu
  stdout — *sgrìobhainn JSON a-mhàin* — gun teachdaireachdan adhartais, gun
  spinners. Thèid mearachdan gu stderr mar `{"error": "...", "detail": "..."}`.
* **Còdan-fàgail seasmhach.** `0` ceart / `1` cleachdadh / `2` dearbhadh / `3`
  frithealaiche / `4` cuibhrichte reata / `5` gun lorg. Faodaidh àidseantan
  brangachadh air iad sin gun mhearachdan cànain nàdarra a mhìneachadh.
* **Gun cheistean eadar-ghnìomhach ann an co-theacsan headless.** Thoir `--yes`
  (no `-y`) do ghnìomhan millteach; thoir `--api-key` no suidhich `OMI_API_KEY`
  gus clàradh eadar-ghnìomhach a sheachnadh.
* **Giùlan ath-dhearbhaidh tròcaireach.** Thèid `429` agus `5xx` ath-dhearbhadh
  le backoff mus tèid an taisbeanadh.

## Dearbhadh (aon turas, leis an duine)

Gheibh an neach-cleachdaidh iuchair API dev bho aplacaid lìn Omi
(`https://app.omi.me` → Developer → API Keys) agus an uair sin:

```bash
omi auth login                          # pasgadh eadar-ghnìomhach; chan eil an iuchair ann an eachdraidh an t-slige
# no
export OMI_API_KEY=omi_dev_...          # sealach, freagarrach airson container
```

## Na còig rudan as trice a nì àidseantan

### 1. Leugh cuimhneachan

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Cruthaich cuimhne

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leugh còmhraidhean

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leugh nithean-gnìomha fosgailte

```bash
omi action-item list --json --open
```

### 5. Cuir crìoch air nì-gnìomha

```bash
omi action-item complete --json a1b2c3d4
```

## API Deasg Ionadail

Nuair a nochdas Omi Desktop an API ionadail aige, faodaidh àidseantan
ceistean a chur mu eachdraidh na sgrìn air an inneal, geàrr-chunntasan, SQL,
agus gnìomhan gun an API dev neòil a chleachdadh:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# no, airson seiseanan sealach:
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

Cuir crìoch air no sguab às gnìomhan a-mhàin nuair a dh'iarras an
neach-cleachdaidh gu soilleir e:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Sgrìobhaidh `omi local screenshot SCREENSHOT_ID --output PATH` an dealbh-sgrìn
gu diosc agus clò-bhuailidh e JSON gu stdout fhathast airson sgriobtaichean.
Thig ID an dealbh-sgrìn mar as trice bho `local search-screen` no SQL thairis
air a' chlàr `screenshots`. Ma thilleas Desktop fàilligeadh structarail leithid
`screenshot_pending`, `screenshot_file_missing`, no `screenshot_chunk_corrupted`,
gleidhidh am modh JSON na raointean `reason`, `hint`, agus `screenshot_id` air
stderr gus an urrainn dha àidseantan ID nas sine ath-dhearbhadh no am bacadh
ceart innse. Dearbh toradh soirbheachail le `file PATH` mus cuir thu gu
innealan lèirsinn iad.

## Eisimpleir: lùb àidseant Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Gairm an CLI omi ann am modh JSON, a' togail mearachd air còdan-fàgail neo-shoirbheachail."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Clò-bhuailidh an CLI mearachdan structarail gu stderr ann am modh JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leugh a h-uile nì-gnìomha fosgailte agus comharraich rud sam bith nas sine na 30 latha mar chrìochnaichte.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## A' làimhseachadh crìochan reata

Cuimhneachan: 120/a san uair. Còmhraidhean: 25/a san uair. Cruthachaidhean
baidse: 15/a san uair.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # reata air a chuingealachadh
    err = json.loads(result.stderr)
    # err["detail"] a' coimhead mar: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Molaidhean

* Cleachd `--profile <name>` ma bhios an àidseant agad a' làimhseachadh
  ioma-chunntasan Omi. Tha a theisteanas fhèin agus a bhonn API fhèin aig gach
  pròifil.
* Cleachd `--api-base http://localhost:8080` airson deuchainn backend ionadail.
* Cleachd `OMI_LOCAL_API_URL` agus `OMI_LOCAL_TOKEN` gus roghainnean API Desktop
  na pròifil a chuir air thairis airson aon ruith.
* Cleachd `--verbose` airson debugging — clàraichidh e `METHOD path → status (Ns)` air stderr
  gun buaidh air stdout, mar sin fuirichidh am modh JSON dligheach.
* Airson susbaint a phìobadh a-steach do chòmhradh, cleachd `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
