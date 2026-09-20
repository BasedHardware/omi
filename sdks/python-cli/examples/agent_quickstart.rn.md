# omi-cli kubw'aba agents (aba programe bakoresha ubwenge bw'ikoranabuhanga)

> Inyoborabigisha ifatika kub'aba agents ari bo ba LLM (Claude Code, Cursor, na bots zawe bwite).

## Icyatumye CLI ari nziza kub'aba agents

* **Amasezerano ya JSON ahamye.** `--json` isoza inyandiko ya JSON ikwiye kuri stdout
  kandi *gusa* inyandiko ya JSON — nta mensho y'iterambere, nta spinners. Amakosa
  ajya kuri stderr nka `{"error": "...", "detail": "..."}`.
* **Kode zo gusoza zihamye.** `0` neza / `1` gukoresha / `2` kwemeza umwirondoro /
  `3` seriveri / `4` kugabanya umuvuduko / `5` ntibonetse. Aba agents bashobora
  guhitamo ukurikije izi kode batasuzugura amakosa y'ururimi rusanzwe.
* **Nta bibazo byo kuganira mu bihe bya headless.** Tanga `--yes` (cyangwa `-y`) ku
  mitangire yangiza; tanga `--api-key` cyangwa shyiraho `OMI_API_KEY` kugira ngo
  wambuke icyo kwinjira mu kuganira.
* **Kwongera kugerageza kubabarira.** `429` na `5xx` bongera kugeragezwa na backoff
  mbere yo kugaragara.

## Kwemeza umwirondoro (inshuro imwe, n'abantu)

Umukoresha abona urufunguzo rwa API rw'iterambere mu porogaramu ya Omi yo ku rubuga
(`https://app.omi.me` → Developer → API Keys) hanyuma:

```bash
omi auth login                          # gushyira mu buryo bwo kuganira; urufunguzo ntiruba mu mateka ya shell
# cyangwa
export OMI_API_KEY=omi_dev_...          # by'agateganyo, biboneye konteneri
```

## Ibintu bitanu abo agents bakora cyane

### 1. Gusoma memorije

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Gukora memorije

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Gusoma ibiganiro

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Gusoma imirimo y'ibikorwa ifunguye

```bash
omi action-item list --json --open
```

### 5. Gushyira akamenyetso ko ikintu cy'ibikorwa cyarangiye

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Iyo Omi Desktop yerekanye API yayo ya local, aba agents bashobora kubaza amateka ya
screenshot kuri gikoresho, inyandiko ngufi, SQL n'imirimo batakoresheje cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# cyangwa, kub'inkino by'agateganyo:
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

Soza cyangwa usize imirimo gusa iyo umukoresha abisabye mu buryo butagaragara:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` yandika screenshot kuri disiki kandi
ikomeje gusoza JSON kuri stdout kub'inyandikoruganda. ID ya screenshot isanzwe iva muri
`local search-screen` cyangwa SQL kuri tabilo ya `screenshots`. Niba Desktop igarutse
ikosa ryateguwe nka `screenshot_pending`, `screenshot_file_missing` cyangwa
`screenshot_chunk_corrupted`, mode ya JSON ibika campos `reason`, `hint` na
`screenshot_id` kuri stderr kugira ngo aba agents bashobore kongera kugerageza na ID
ishaje cyangwa bamenyeshe ikibazo nyacyo. Gena neza ibyasohotse neza ukoresheje `file
PATH` mbere yo kubiha ibikoresho byo kureba.

## Urugero rukorwa: loop ya agent muri Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ita CLI ya omi muri mode ya JSON, itera exception ku kode zo gusoza zitanzwe neza."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI isoza amakosa yateguwe kuri stderr muri mode ya JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Soma imirimo y'ibikorwa ifunguye yose ushyire akamenyetso ko cyarangiye kuri iyo ishaje iminsi 30.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gukemura ugabanya umuvuduko

Memorije: 120/isaha. Ibiganiro: 25/isaha. Gukora byinshi icyarimwe: 15/isaha.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # ugabanya umuvuduko
    err = json.loads(result.stderr)
    # err["detail"] isa nka: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Uburambe

* Koresha `--profile <name>` niba agent yawe ikoresha konti nyinshi za Omi. Buri profile
  ifite ubwambere bwayo n'ibanze rya API.
* Koresha `--api-base http://localhost:8080` kugirango ugerageze backend ya local.
* Koresha `OMI_LOCAL_API_URL` na `OMI_LOCAL_TOKEN` kugirango uhindure amakuru ya
  Desktop API ya profile mu rugendo rumwe.
* Koresha `--verbose` kugirango ubone amakosa — yandika `METHOD path → status (Ns)` kuri
  stderr utagize icyo ahindura kuri stdout, nuko mode ya JSON ikomeza kuba ikwiye.
* Kugirango ushyire ibikubiyemo mu kiganiro, koresha `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```