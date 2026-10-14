# omi-cli pi agenti

> Guida pràctica pi harness guidati di LLM (Claude Code, Cursor, i tò stessi bot).

## Picchì la CLI è amica pi agenti

* **Cuntrattu JSON stabbili.** `--json` emetti un documentu JSON vàlitu nna stdout e
  *sulu* un documentu JSON — senza missagghi di prugressu, senza spinner. L'erruri
  vannu nna stderr comu `{"error": "...", "detail": "..."}`.
* **Còdici di nisciuta stabbili.** `0` bonu / `1` usu / `2` auth / `3` server /
  `4` limitu di vilucità / `5` nun truvatu. Li agenti ponnu ramificari nna chisti
  senza analizzari erruri nna lingwa naturali.
* **Senza prompt interattivi nna cuntesti headless.** Passa `--yes` (o `-y`) ê
  cumanni distruttivi; passa `--api-key` o metti `OMI_API_KEY` pi saltari lu
  login interattivu.
* **Cumpurtamentu di ritentu pirdunanu.** `429` e `5xx` vennu ritentati cu
  backoff prima di nascìri.

## Auth (na vota, di l'omu)

L'utenti pigghia na chiavi dev API dâ applicazzioni web Omi
(`https://app.omi.me` → Developer → API Keys) e o:

```bash
omi auth login                          # ncullaggiu interattivu; la chiavi nun resta nna storia dâ shell
# o
export OMI_API_KEY=omi_dev_...          # efimera, megghiu pi cuntinituri
```

## Li cincu cosi chi li agenti fannu cchiù

### 1. Leggiri mimorii

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Criari na mimoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leggiri cunvirsazzioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggiri punti di azzioni aperti

```bash
omi action-item list --json --open
```

### 5. Marcari un puntu di azzioni comu fattu

```bash
omi action-item complete --json a1b2c3d4
```

## API lucali di Desktop

Quannu Omi Desktop espunni la so API lucali, li agenti ponnu addumannari la
storia dû schirmu dû dispusitivu, ricapitulazzioni, SQL e travagghi senza usari
l'API dev dû cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pi sessioni efimiri:
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

Cumpleta o cancella travagghi sulu quannu l'utenti lu dumanna chiarimenti:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrivi lu screenshot nna discu
e stampa ancora JSON nna stdout pi script. L'ID dû screenshot veni di sòlitu di
`local search-screen` o SQL ncapu a tabella `screenshots`. Si Desktop ritorna n'erruri
strutturatu comu `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, lu modu JSON preserva li campi `reason`, `hint` e
`screenshot_id` nna stderr accussì li agenti ponnu ritentari un ID cchiù vecchiu
o signalari lu bloccu esattu. Validati li nisciuti riesciti cu `file PATH` prima
di passarli ê strumenti di vistioni.

## Esempiu travagghiatu: cclu d'agenti nna Python

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

## Gistiun di limiti di vilucità

Mimorii: 120/ura. Cunvirsazzioni: 25/ura. Criazzioni nna lotti: 15/ura.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suggerimenti

* Usa `--profile <name>` si lu tò agenti gestisci diversi cunti Omi. Ogni prufilu
  àvi li so credenziali e la so basi API.
* Usa `--api-base http://localhost:8080` pi test backend lucali.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` pi sostituiri li mpustazzioni
  de l'API lucali Desktop dû prufilu pi na esecuzzioni.
* Usa `--verbose` pi debug — reggistra `METHOD path → status (Ns)` nna stderr
  senza affittari stdout, cussì lu modu JSON resta vàlitu.
* Pi pipeari cuntinutu nna na cunvirsazzioni, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
