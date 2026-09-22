# omi-cli fun awon aṣoju (Agents)

> Itọsọna to wulo fun awọn agbegbe ti LLM n ṣakoso (Claude Code, Cursor, awọn bot tirẹ).

## Idi ti CLI fi dara fun awọn aṣoju

* **Adehun JSON ti o duro ṣinṣin.** `--json` n mu iwe JSON to wulo jade si `stdout` ati
  *nikan* iwe JSON: ko si awọn ifiranṣẹ ilọsiwaju tabi awọn itọka ikojọpọ. Awọn aṣiṣe lọ si
  `stderr` gẹgẹbi `{"error": "...", "detail": "..."}`.
* **Awọn koodu ijade ti o duro ṣinṣin.** `0` aṣeyọri / `1` aṣiṣe lilo / `2` ijẹrisi / `3` olupin / `4` opin
  iyara ti de (rate limit) / `5` ko ri i. Awọn aṣoju le ya awọn ẹka lori awọn koodu wọnyi laisi iwulo lati ṣe itupalẹ
  awọn aṣiṣe ede adayeba.
* **Ko si awọn ibeere ibaraenisọrọ ni awọn agbegbe headless.** Fi `--yes` (tabi `-y`) ranṣẹ fun
  awọn aṣẹ iparun; fi `--api-key` ranṣẹ tabi ṣeto `OMI_API_KEY` lati fo
  iwọle ibaraenisọrọ.
* **Iwa atungbiyanju ti o lagbara.** Awọn aṣiṣe `429` ati `5xx` ni a tun gbiyanju pẹlu ifẹhinti ti o pọ si
  ṣaaju ki wọn to han.

## Ijẹrisi (lẹẹkan ṣoṣo, ti eniyan n ṣe)

Olumulo gba kọkọrọ API idagbasoke lati inu app wẹẹbu Omi
(`https://app.omi.me` → Developer → API Keys) ati ṣe ọkan ninu awọn aṣayan:

```bash
omi auth login                          # lẹmọ ibaraenisọrọ; kọkọrọ ko duro ninu itan ikarahun
# tabi
export OMI_API_KEY=omi_dev_...          # igba diẹ, o dara fun awọn apoti (containers)
```

## Awọn iṣe marun ti o wọpọ julọ fun awọn aṣoju

### 1. Ka awọn iranti (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Ṣẹda iranti kan

```bash
omi memory create --json "Olumulo fẹran ipo dudu" --category lifestyle
```

### 3. Ka awọn ibaraẹnisọrọ

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ka awọn ohun iṣe ti o ṣii

```bash
omi action-item list --json --open
```

### 5. Samisi ohun iṣe bi o ti pari

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop Local API

Nigbati Omi Desktop ba ṣii API agbegbe rẹ, awọn aṣoju le beere itan
iboju lori ẹrọ naa, awọn akopọ, SQL, ati awọn iṣẹ-ṣiṣe laisi lilo API idagbasoke awọsanma:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# tabi fun awọn akoko igba diẹ:
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

Pari tabi pa awọn iṣẹ-ṣiṣe rẹ nikan nigbati olumulo ba beere ni pato:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` n fipamọ sikirinisoti si disiki ati
tẹsiwaju lati tẹ JSON jade si `stdout` fun awọn iwe afọwọkọ. ID sikirinisoti maa n wa
lati `local search-screen` tabi ibeere SQL lori tabili `screenshots`. Ti Desktop ba
da aṣiṣe eto pada gẹgẹbi `screenshot_pending`, `screenshot_file_missing`,
tabi `screenshot_chunk_corrupted`, ipo JSON n tọju awọn aaye `reason`, `hint`, ati
`screenshot_id` sinu `stderr` ki awọn aṣoju le tun gbiyanju pẹlu ID ti tẹlẹ tabi jabo
idi pataki ti idaduro naa. Daju awọn iṣelọpọ aṣeyọri pẹlu `file PATH` ṣaaju fifiranṣẹ
si awọn irinṣẹ iran (vision tools).

## Apẹẹrẹ ti o wulo: Loop aṣoju ni Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """N pe omi CLI ni ipo JSON, n gbe iyasọtọ dide lori awọn koodu ijade ti kii ṣe odo."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI n tẹ awọn aṣiṣe ti a ṣeto jade si stderr ni ipo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi jade pẹlu koodu {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ka gbogbo awọn ohun iṣe ti o ṣii ki o samisi awọn ti o ti kọja ọgbọn ọjọ bi o ti pari.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Ṣiṣakoso awọn opin iyara (Rate Limits)

Awọn iranti: 120/wákàtí. Awọn ibaraẹnisọrọ: 25/wákàtí. Awọn ẹda ipele: 15/wákàtí.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # opin iyara ti de
    err = json.loads(result.stderr)
    # err["detail"] ni ọna kika: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Awọn imọran

* Lo `--profile <orukọ>` ti aṣoju rẹ ba n ṣakoso ọpọlọpọ awọn akọọlẹ Omi. Olukuluku
  profaili n tọju awọn iwe-ẹri tirẹ ati ipilẹ API.
* Lo `--api-base http://localhost:8080` fun idanwo backend agbegbe.
* Lo `OMI_LOCAL_API_URL` ati `OMI_LOCAL_TOKEN` lati bori iṣeto API Desktop agbegbe ti
  profaili fun ṣiṣe ẹyọkan.
* Lo `--verbose` fun n ṣatunṣe aṣiṣe: o ṣe igbasilẹ `METHOD path status (Ns)` sinu `stderr`
  laisi fọwọkan `stdout`, nitorinaa mimu ṣiṣan JSON to wulo duro.
* Lati fi akoonu ranṣẹ si ibaraẹnisọrọ nipasẹ pipe, lo `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
