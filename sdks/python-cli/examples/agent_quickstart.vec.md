# omi-cli par agenti

> Guida pratega par harness guidadi da LLM (Claude Code, Cursor, i to stessi bot).

## Parché la CLI xe amiga par agenti

* **Contrato JSON stabiłe.** `--json` el emete un documento JSON valido a stdout e
  *soło* un documento JSON — sensa messaggi de progresso, sensa spinner. I erori
  i va a stderr come `{"error": "...", "detail": "..."}`.
* **Còdeghi de sortida stabiłi.** `0` ben / `1` uso / `2` auth / `3` server /
  `4` lìmite de vełocità / `5` no cata. I agenti i połe ramificare su cuesti
  sensa anałixare erori in łengua naturałe.
* **No prompt interativi in contesti headless.** Pasa `--yes` (o `-y`) ai comandi
  destrutivi; pasa `--api-key` o meti `OMI_API_KEY` par saltare el login interativo.
* **Comportamento de retry perdonàr.** `429` e `5xx` i vien ripetii co backoff
  prima de venir fora.

## Auth (na volta, da l'omo)

L'utente el ciapa na ciave dev API da l'aplicasion web Omi
(`https://app.omi.me` → Developer → API Keys) e o:

```bash
omi auth login                          # incołà interativo; la ciave no resta in storia de ła shełł
# o
export OMI_API_KEY=omi_dev_...          # efìmera, ideale par contenidori
```

## Le cinque robe che i agenti fa de pì

### 1. Lèxere memorie

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare na memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lèxere conversasioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lèxere ponti de azione verci

```bash
omi action-item list --json --open
```

### 5. Segnare un ponto de azione come fato

```bash
omi action-item complete --json a1b2c3d4
```

## API locałe de Desktop

Co Omi Desktop espone ła so API locałe, i agenti i połe interogare ła storia
del schermo del dispositivo, i recapit, SQL e i laori sensa usare l'API dev
del cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, par sessioni efìmere:
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

Conpleta o ełimina laori soło co l'utente lo ciama ciaro:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive el screenshot ał disco
e stampa ancora JSON a stdout par script. L'ID del screenshot vien de sołito da
`local search-screen` o SQL sora ła tabeła `screenshots`. Se Desktop torna n'erore
struturà come `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, el modo JSON preserva i campi `reason`, `hint` e
`screenshot_id` a stderr cussì i agenti i połe riproar un ID pì vecio o
segnalare el błoco esato. Vałida łe nisciute riescite co `file PATH` prima de
passarli ai strumenti de vision.

## Ezempio łavorà: çcio d'agente in Python

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

## Jestion dei lìmiti de vełocità

Memorie: 120/ora. Conversasioni: 25/ora. Creasioni in łote: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consiji

* Dopara `--profile <name>` se el to agente xestise tanti conti Omi. Ogni profiło
  ga łe so credensiałi e ła so base API.
* Dopara `--api-base http://localhost:8080` par test backend locałi.
* Dopara `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` par sostituire łe inpostasion
  de l'API locałe Desktop del profiło par na esecusion.
* Dopara `--verbose` par debug — scrive `METHOD path → status (Ns)` a stderr
  sensa afetare stdout, cussì el modo JSON resta vałido.
* Par pipear contegnuo in na conversasion, dopara `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
