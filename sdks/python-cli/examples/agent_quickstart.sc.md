# omi-cli pro agentes

> Ghia pratica pro harnesses ghiaos de LLM (Claude Code, Cursor, is bots tuos).

## Pro ite sa CLI est amiga de is agentes

* **Contratu JSON istabile.** `--json` emit unu documentu JSON validu in stdout e
  *petzi* unu documentu JSON — sena messagios de progressu, sena spinner. Is errors
  andant in stderr comente `{"error": "...", "detail": "..."}`.
* **Codigos de essida istabiles.** `0` bene / `1` impreu / `2` auth / `3` server /
  `4` limite de lestridade / `5` non agatadu. Is agentes podent ramare in custos
  sena analizare errors in limba naturali.
* **Sena prompt interativos in contestos headless.** Passa `--yes` (o `-y`) a is
  comandos destrutivos; passa `--api-key` o imposta `OMI_API_KEY` pro satare su
  login interativu.
* **Cumportamentu de retry perdonante.** `429` e `5xx` funt torrados a proare
  cun backoff prima de essire.

## Auth (una borta, dae s'omine)

S'utente pigad una crae dev API dae s'aplicatzione web Omi
(`https://app.omi.me` → Developer → API Keys) e o:

```bash
omi auth login                          # incollu interativu; sa crae non restat in s'istoria de sa shell
# o
export OMI_API_KEY=omi_dev_...          # efimera, megliu pro containers
```

## Is chimbe cosas chi is agentes faghent de prus

### 1. Leghe memòrias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crea una memòria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leghe cunnversatziones

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leghe puntos de atzione abertos

```bash
omi action-item list --json --open
```

### 5. Marca unu puntu de atzione comente faitu

```bash
omi action-item complete --json a1b2c3d4
```

## API locale de Desktop

Cando Omi Desktop esponet sa API locale, is agentes podent preguntare s'istoria
de s'ischermu de su dispositivu, ricapitolos, SQL e traballos sena imperare sa
API dev de su cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pro sessiones efimeras:
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

Cumpleta o annulla traballos petzi cando s'utente lu pedet a craru:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` iscriet su screenshot in su
discu e imprentat ancora JSON in stdout pro scripts. S'ID de su screenshot benit
de normali de `local search-screen` o SQL in sa tabella `screenshots`. Si Desktop
torrat un'error struturadu comente `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, su modu JSON conservat is campos `reason`, `hint`
e `screenshot_id` in stderr duncas is agentes podent torrare a proare un ID prus
betzu o raportare su blocu esattu. Valida is essidas bonas cun `file PATH` prima
de ddas passare a is strumentos de visione.

## Esempiu traballadu: cclu de agente in Python

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

## Gestione de is limites de lestridade

Memòrias: 120/h. Cunnversatziones: 25/h. Criatziones in lotos: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cunsìgios

* Impera `--profile <name>` si s'agente tuo gestit medas contos Omi. Cada profilu
  tenet is credentziales e sa base API suos.
* Impera `--api-base http://localhost:8080` pro tests de backend locales.
* Impera `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` pro sostituire is impostatziones
  de s'API locale Desktop de su profilu pro una esecutzione.
* Impera `--verbose` pro debug — registrat `METHOD path → status (Ns)` in stderr
  sena afettare stdout, duncas su modu JSON restat validu.
* Pro pipeare cuntenutu in una cunnversatzione, impera `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
