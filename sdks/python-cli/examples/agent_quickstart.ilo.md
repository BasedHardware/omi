# omi-cli para kadagiti ahente

> Praktikal a giya para kadagiti LLM-driven a harness (Claude Code, Cursor, dagiti bukodmo a bot).

## Apay a ti CLI ket ahente-friendly

* **Stable a JSON contract.** Ti `--json` agiparang iti balido a JSON document iti stdout ken
  *JSON document laeng* — awan progress messages, awan spinners. Dagiti biddut mapan iti
  stderr kas `{"error": "...", "detail": "..."}`.
* **Stable a exit codes.** `0` ok / `1` panagusar / `2` auth / `3` server / `4` rate
  limited / `5` saan a mabirukan. Dagiti ahente makabaelda nga agbranch kadagitoy a code
  nga awan panag-parse kadagiti natural-language a biddut.
* **Awan interactive prompts kadagiti headless a konteksto.** Ipasa ti `--yes` (wenno `-y`)
  kadagiti destructive a command; ipasa ti `--api-key` wenno iset ti `OMI_API_KEY` tapno
  maliklikan ti interactive a panaglogin.
* **Mapakawan a retry a kababalin.** Dagiti `429` ken `5xx` maulit-ulit nga addaan backoff
  sakbay nga agparang.

## Auth (mamingsan, aramiden ti tao)

Ti user ket mangala iti dev API key manipud iti Omi web app
(`https://app.omi.me` → Developer → API Keys) ken aramidenna ti maysa kadagitoy:

```bash
omi auth login                          # interactive a panagpaste; ti key saan a mapan iti shell history
# wenno
export OMI_API_KEY=omi_dev_...          # ephemeral, maitutop iti container
```

## Dagiti lima a banag a kaaduan nga aramiden dagiti ahente

### 1. Agbasa kadagiti memory

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Agaramid iti memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Agbasa kadagiti conversation

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Agbasa kadagiti open action item

```bash
omi action-item list --json --open
```

### 5. Markahan nga nalpas ti action item

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

No ti Omi Desktop iparangna ti local API na, dagiti ahente makapagsaludsodda kadagiti
on-device screen history, recaps, SQL, ken task nga awan panagusar iti cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# wenno, para kadagiti ephemeral a session:
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

Kompletoen wenno ikkaten dagiti task laeng no ti user ket klaro a kiddawenna:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Ti `omi local screenshot SCREENSHOT_ID --output PATH` agsursurat iti screenshot iti disk
ken agiprinta pay laeng iti JSON iti stdout para kadagiti script. Ti screenshot ID ket
kadawyan a naggapu iti `local search-screen` wenno SQL iti `screenshots` a table. No ti
Desktop agisubli iti structured a pannakapaay a kas iti `screenshot_pending`,
`screenshot_file_missing`, wenno `screenshot_chunk_corrupted`, ti JSON mode ket
taginayonenna dagiti `reason`, `hint`, ken `screenshot_id` a field iti stderr tapno dagiti
ahente makapagretry iti daan nga ID wenno makapagreport iti eksakto a blocker. Validaren
dagiti naballigi a output iti `file PATH` sakbay nga ipasa kadagiti vision tool.

## Naaramid a pagarigan: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Awagan ti omi CLI iti JSON mode, nga agraise kadagiti saan a success nga exit code."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Ti CLI agiprinta kadagiti structured a biddut iti stderr iti JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Basaen dagiti amin a open action item ken markahan a complete dagiti mas daan ngem 30 nga aldaw.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Panangimanehar kadagiti rate limit

Dagiti memory: 120/hr. Dagiti conversation: 25/hr. Batch creates: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitado ti rate
    err = json.loads(result.stderr)
    # kastoy ti langa ti err["detail"]: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Dagiti tip

* Usaren ti `--profile <name>` no ti agent mo ket mangimanehar kadagiti adu nga Omi
  account. Ti tunggal profile ket addaan iti bukodna a credential ken API base.
* Usaren ti `--api-base http://localhost:8080` para iti local backend testing.
* Usaren dagiti `OMI_LOCAL_API_URL` ken `OMI_LOCAL_TOKEN` tapno ma-override dagiti
  profile-local Desktop API setting para iti maysa a run.
* Usaren ti `--verbose` para iti debugging — aglog daytoy iti `METHOD path → status (Ns)`
  iti stderr nga awan epektona iti stdout, isu a ti JSON mode ket agtalinaed a balido.
* Para iti panagpipe iti content nga mapan iti conversation, usaren ti `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
