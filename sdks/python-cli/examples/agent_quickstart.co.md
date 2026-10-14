# omi-cli per l'agenti

> Guida pratica per l'harness guidati da LLM (Claude Code, Cursor, i to pròprii bot).

## Parchì a CLI hè amica per l'agenti

* **Cuntrattu JSON stabile.** `--json` emette un documentu JSON valide nant'à stdout è
  *solu* un documentu JSON — senza missaghji di prugressu, senza spinner. L'errore
  vanu nant'à stderr cum'è `{"error": "...", "detail": "..."}`.
* **Codici d'esciuta stabile.** `0` bè / `1` usu / `2` auth / `3` servitore /
  `4` limite di velucità / `5` micca truvatu. L'agenti ponu ramificà nant'à questi
  senza analizà errore in lingua naturale.
* **Senza prompt interattivi in cuntesti headless.** Passa `--yes` (o `-y`) à i
  cumanni distruttivi; passa `--api-key` o metti `OMI_API_KEY` per scappà u
  login interattivu.
* **Cumportamentu di ritentu perdonèvule.** `429` è `5xx` sò ritentati cun
  backoff prima di spuntà.

## Auth (na volta, da l'omu)

L'utilizadore piglia una chjave dev API da l'applicazione web Omi
(`https://app.omi.me` → Developer → API Keys) è o:

```bash
omi auth login                          # incollu interattivu; a chjave ùn resta micca in a storia di a shell
# o
export OMI_API_KEY=omi_dev_...          # efimeru, megliu per i cuntinidori
```

## E cinque cose chì l'agenti fanu di più

### 1. Leghje mimorie

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creà una mimoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leghje cunnversazioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leghje punti d'azzione aperti

```bash
omi action-item list --json --open
```

### 5. Marca un puntu d'azzione cum'è fattu

```bash
omi action-item complete --json a1b2c3d4
```

## API lucale di Desktop

Quandu Omi Desktop esponne a so API lucale, l'agenti ponu dumandà a storia di
u screnu di u dispusitivu, ricapitulazioni, SQL è travagli senza utilizà l'API
dev di a nuvola:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, per e sessioni efimere:
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

Cumpleta o annulla travagli solu quandu l'utilizadore u dumanda chjaru:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive u screenshot nant'à u
discu è stampa ancora JSON nant'à stdout per scripts. L'ID di u screenshot veni
di solitu da `local search-screen` o SQL nant'à a tavula `screenshots`. S'è
Desktop torna un'errore strutturatu cum'è `screenshot_pending`,
`screenshot_file_missing` o `screenshot_chunk_corrupted`, u modu JSON conserva
i campi `reason`, `hint` è `screenshot_id` nant'à stderr cusì l'agenti ponu
ritentà un ID più vechju o raportà u bloccu esattu. Valida e nisciute buni cun
`file PATH` prima di passà li à i strumenti di visione.

## Esempiu travagliatu: ciclu d'agente in Python

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

## Gestiò di i limiti di velucità

Mimorie: 120/h. Cunnversazioni: 25/h. Creazzioni in lotti: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cunsiglii

* Usa `--profile <name>` s'è u to agente gestisce parechji conti Omi. Ogni profilu
  hà i so credenziali è a so base API.
* Usa `--api-base http://localhost:8080` per e prove di backend lucali.
* Usa `OMI_LOCAL_API_URL` è `OMI_LOCAL_TOKEN` per sustituì i paràmetri
  de l'API lucale Desktop di u profilu per una esecuzione.
* Usa `--verbose` per debug — registra `METHOD path → status (Ns)` nant'à stderr
  senza affittà stdout, cusì u modu JSON resta valide.
* Per pipeà cuntenutu in una cunnversazione, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
