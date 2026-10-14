# omi-cli mo soāgafua

> Ta'iala atoā mo harness e fa'atautaia e LLM (Claude Code, Cursor, lau bot lava ia).

## Aiseā e lelei ai le CLI mo soāgafua

* **Konekarate JSON mautu.** `--json` e tu'uina atu se pepa JSON sa'o i le stdout ma
  *na'o* se pepa JSON — 'a'ai fe'au fa'asolosolo, 'a'ai spinner. Nā sese e alu i le
  stderr e pei `{"error": "...", "detail": "..."}`.
* **Numera pulega mautu.** `0` lelei / `1` fa'aoga / `2` auth / `3` server /
  `4` tapula'a sao / `5` 'a'ai maua. E mafai e soāgafua ona filifili i ia e aunoa ma
  le su'esu'e i sese i le gagana fa'anatura.
* **'A'ai prompt interactive i context headless.** Tu'uina atu `--yes` (po'o `-y`)
  i poloaiga fa'aleaga; tu'uina atu `--api-key` pe seti `OMI_API_KEY` e solopulea
  le login interactive.
* **Uiga fa'aaloalō retry.** `429` ma `5xx` e toe taumafai ma le backoff a'o le'i
  alia'ia.

## Auth (tasi le taimi, e le tagata)

E maua e le tagata fa'aoga se ki dev API mai le app web Omi
(`https://app.omi.me` → Developer → API Keys) ma po'o:

```bash
omi auth login                          # fa'apipi'i interactive; le ki e 'a'ai tumau i le talafa'asolopito
# po'o
export OMI_API_KEY=omi_dev_...          # fa'ata'ita'i, lelei mo ipu
```

## Nā mea e lima e sili ona faia e soāgafua

### 1. Faitau manatuga

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Fatu se manatu

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Faitau talanoaga

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Faitau mea galue e tatala

```bash
omi action-item list --json --open
```

### 5. Fa'ailoga se mea galue ua mae'a

```bash
omi action-item complete --json a1b2c3d4
```

## API le lotoifale o Desktop

Pe a fa'aalia e Omi Desktop lona API lotoifale, e mafai e soāgafua ona fesili i
le talafa'asolopito o le lau o le masini, le fa'ato'ilima, SQL, ma galuega e
aunoa ma le fa'aoga o le API dev i le ao:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# po'o, mo sauniga fa'ata'ita'i:
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

Fa'amae'a pe tape rānei galuega pe a manino le tagata fa'aoga:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` e tusia le screenshot i le
disk ma e lolomi pea le JSON i le stdout mo scripts. O le ID screenshot e masani
ona sau mai `local search-screen` pe SQL i luga o le laulau `screenshots`. Afai
e toe tu'uina e Desktop se sese fa'atulagaina e pei `screenshot_pending`,
`screenshot_file_missing`, pe `screenshot_chunk_corrupted`, o le mode JSON e
fa'asaoina nā vaega `reason`, `hint`, ma `screenshot_id` i le stderr ina ia mafai
e soāgafua ona toe taumafai i se ID tuai po'o lipoti le poloka sa'o. Fa'amaonia
tu'uiga lelei ma `file PATH` a'o le'i tu'uina i meafaigaluega va'aiga.

## Fa'ata'ita'iga ua fa'atino: fa'apu'upu'u 'ēgenta Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Pulea tapula'a sao

Manatuga: 120/h. Talanoaga: 25/h. Fa'atulagaina fa'atino: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Fautuaga

* Fa'aoga `--profile <name>` pe a pulea e lau 'ēgenta ni teugatupe Omi 'ese'ese.
  O pūlumi uma lo latou tofi credential ma le fa'avae API.
* Fa'aoga `--api-base http://localhost:8080` mo su'ega backend lotoifale.
* Fa'aoga `OMI_LOCAL_API_URL` ma `OMI_LOCAL_TOKEN` e suia seti o le API lotoifale
  o le Desktop o le pūlumi mo tasi tamoʻe.
* Fa'aoga `--verbose` mo le fa'asa'o — e lolomi `METHOD path → status (Ns)` i le
  stderr e aunoa ma le a'afiaga o le stdout, o le mode JSON e tumau pea i le sa'o.
* E pipe le 'ike i le talanoaga, fa'aoga `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
