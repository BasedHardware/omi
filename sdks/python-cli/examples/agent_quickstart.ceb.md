# omi-cli alang sa mga ahente

> Praktikal nga giya alang sa mga LLM-driven nga harness (Claude Code, Cursor, imong kaugalingong mga bot).

## Ngano nga ang CLI angay sa mga ahente

* **Stable nga JSON contract.** Ang `--json` nagpagawas og balidong JSON document sa stdout ug
  *JSON document lamang* — walay progress messages, walay spinners. Ang mga sayop moadto sa
  stderr isip `{"error": "...", "detail": "..."}`.
* **Stable nga exit codes.** `0` ok / `1` paggamit / `2` auth / `3` server / `4` rate
  limited / `5` wala makita. Ang mga ahente makahimo og branch base niini nga mga code
  nga walay pag-parse sa natural-language nga mga sayop.
* **Walay interactive prompts sa headless contexts.** Ihatag ang `--yes` (o `-y`) sa
  destructive nga mga command; ihatag ang `--api-key` o i-set ang `OMI_API_KEY` aron
  malikayan ang interactive login.
* **Mapinasayloon nga retry behavior.** Ang `429` ug `5xx` i-retry uban ang backoff
  sa dili pa mosurface.

## Auth (usa ka beses, gihimo sa tawo)

Ang user makakuha og dev API key gikan sa Omi web app
(`https://app.omi.me` → Developer → API Keys) ug mohimo sa usa niini:

```bash
omi auth login                          # interactive paste; ang key wala sa shell history
# o
export OMI_API_KEY=omi_dev_...          # ephemeral, angay sa container
```

## Ang lima ka butang nga pinakadaghanon sa mga ahente

### 1. Pagbasa sa mga memory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Paghimo og memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Pagbasa sa mga conversation

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Pagbasa sa open action items

```bash
omi action-item list --json --open
```

### 5. Pagmarka og action item nga nahuman

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Kung ang Omi Desktop mag-expose sa iyang local API, ang mga ahente makapangutana sa
on-device screen history, recaps, SQL, ug tasks nga dili mogamit sa cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, alang sa ephemeral sessions:
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

Kompletoha o papasa ang mga task lamang kung ang user klaro nga naghangyo:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Ang `omi local screenshot SCREENSHOT_ID --output PATH` nagsulat sa screenshot sa disk
ug nagpadayon sa pag-print og JSON sa stdout alang sa mga script. Ang screenshot ID
kasagarang gikan sa `local search-screen` o SQL sa `screenshots` table. Kung ang Desktop
mobalik og structured failure sama sa `screenshot_pending`, `screenshot_file_missing`,
o `screenshot_chunk_corrupted`, ang JSON mode magpreserba sa `reason`, `hint`, ug
`screenshot_id` fields sa stderr aron ang mga ahente makaretry sa mas daan nga ID o
makareport sa eksaktong blocker. I-validate ang malampusong outputs gamit ang `file PATH`
sa dili pa ipasa sa vision tools.

## Ehemplo: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Tawga ang omi CLI sa JSON mode, nga mo-raise kung dili success ang exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Ang CLI nag-print og structured errors sa stderr sa JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Basaha ang tanang open action items ug markahi nga complete ang mas daan pa sa 30 ka adlaw.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Pagdumala sa rate limits

Mga memory: 120/hr. Mga conversation: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitado sa rate
    err = json.loads(result.stderr)
    # ingon ani ang hitsura sa err["detail"]: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mga tip

* Gamita ang `--profile <name>` kung ang imong agent nagdumala og daghang Omi
  accounts. Ang matag profile adunay kaugalingong credential ug API base.
* Gamita ang `--api-base http://localhost:8080` alang sa local backend testing.
* Gamita ang `OMI_LOCAL_API_URL` ug `OMI_LOCAL_TOKEN` aron ma-override ang
  profile-local Desktop API settings alang sa usa ka run.
* Gamita ang `--verbose` alang sa debugging — nag-log kini og `METHOD path → status (Ns)`
  sa stderr nga dili moapekto sa stdout, aron ang JSON mode magpabilin nga balido.
* Alang sa pag-pipe og content ngadto sa conversation, gamita ang `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
