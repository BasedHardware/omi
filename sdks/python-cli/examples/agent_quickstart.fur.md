# omi-cli pai agints

> Gjuide pratic pal sgarât LLM (Claude Code, Cursor, tu bagns tuçs).

## Perché il CLI al è amichevol pai agints

* **JSON contract stabil.** `--json` e mande un document JSON valit sul stdout e
  *nomai* un document JSON — nissun messaç di progress, nissune spinner. Lis erors va a
  stderr come `{"error": "...", "detail": "..."}`.
* **Exit codes stabil.** `0` vut / `1` jame / `2` auth / `3` server /  `4` rate
  limited / `5` no cjatât. Agints puedin ramificâ su chesti cedure cence interpretâ
  erors in lenghe naturâl.
* **Nissune domeande interatifs in contests headless.** Passe `--yes` (o `-y`) ai
  comands distrutivs; passe `--api-key` o met OMI_API_KEY par saltâ il login interativ.
* **Riprov implicit.** `429` e `5xx` venin riprovâts cun backoff prime di mostrâts.

## Auth (une volte, dal uman)

L'utent cjate une API key di svilup de l'app web Omi
(`https://app.omi.me` → Developer → API Keys) e:

```bash
omi auth login                          # paste interativ; la clâf no rest in shell history
# o
export OMI_API_KEY=omi_dev_...          # efemer, amichevol pai containers
```

## Lis cincs cosas che agints fasin plui spess

### 1. Lei memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crene une memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lei conversazions

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lei azions noises

```bash
omi action-item list --json --open
```

### 5. Segne une azion come fadade

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop locâl

Cuant Omi Desktop mostr la sô API locâl, agints puedin interrogâ la storie des ecrans
dal dispositîv, i recap, SQL e tasks cence doprâ la cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, par sessions efemers:
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

Done completâ o eliminâ tasks sol se l'utent al dìs clarament:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive la screenshot su disc e
ognora stampe JSON sul stdout pai scripts. Il screenshot ID al ven di solit di
`local search-screen` o SQL te tabele `screenshots`. Se Desktop rite une failur
struturade come `screenshot_pending`, `screenshot_file_missing`,
o `screenshot_chunk_corrupted`, la modalit JSON mantien i camps `reason`, `hint` e
`screenshot_id` sul stderr par percui agints puedin riprovâ cun un ID plui vieli o
rapurtâ il blocâç esat. Validade i output ricjuits cun `file PATH` prime di doprâs
cuns agints vision.

## Esempl pratic: loop di agint Python

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

## Come gjestionâ i limits di rait

Memories: 120/ore. Conversazions: 25/ore. Creazions in lote: 15/ore.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cjefis

* Doprâ `--profile <name>` se il agint al lavor su plui accounts Omi. Ogni
  profile al à il so credenzial e la so base API.
* Doprâ `--api-base http://localhost:8080` par tests dal backend locâl.
* Doprâ `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` par suplantâ la configurazion
  Desktop API de une single esecuzion.
* Doprâ `--verbose` par debug — al zorn `METHOD path → status (Ns)` sul stderr
  cence influenzâ il stdout, par cui la modalit JSON reste valit.
* Par canalizâ contnût te une conversazion, doprâ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
