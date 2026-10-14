# omi-cli p'agenti

> Guida pratteca p'harness guidati 'a LLM (Claude Code, Cursor, 'e tò stesse bot).

## Pecché a CLI è amica p'agenti

* **Cuntrattu JSON stabil.** `--json` emette nu documentu JSON vàlitu a stdout e
  *sulu* nu documentu JSON — senza missaggi 'e prugressu, senza spinner. L'errure
  vannu a stderr comm'a `{"error": "...", "detail": "..."}`.
* **Codice 'e nisciuta stabil.** `0` bonu / `1` usu / `2` auth / `3` server /
  `4` limite 'e vilucità / `5` nun truvatu. L'agenti ponno ramificari ncoppa
  chisti senza analizzari errure nna lengua naturale.
* **Senza prompt interattivi nna cuntesti headless.** Passa `--yes` (o `-y`) ê
  cumanne distruttive; passa `--api-key` o metti `OMI_API_KEY` pe saltari lu
  login interattivu.
* **Cumportamentu 'e ritentu perdonàr.** `429` e `5xx` vennu ritentati cu
  backoff primma 'e nascìri.

## Auth (na vota, d''o ggnato)

L'utenti pigghia na chiave dev API d''a applicazzione web Omi
(`https://app.omi.me` → Developer → API Keys) e o:

```bash
omi auth login                          # 'ncollaggiu interattivu; a chiave nun resta nna storia d''a shell
# o
export OMI_API_KEY=omi_dev_...          # efimera, meglio p'cuntinituri
```

## E cinque cose ch''e agenti fanno cchiù

### 1. Leggere mimorie

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare na mimoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leggere cummersazzioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggere punti 'e azzioni apierte

```bash
omi action-item list --json --open
```

### 5. Marcari nu puntu 'e azzioni comm'a fattu

```bash
omi action-item complete --json a1b2c3d4
```

## API lucale 'e Desktop

Quannu Omi Desktop espone a so API lucale, l'agenti ponno addumannari a storia
d''o schermo d''o dispusitivu, ricapitulazzioni, SQL e travagli senza usari
l'API dev d''o cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pe sessioni efimere:
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

Cumpleta o cancella travagli sulu quannu l'utenti lu dumanna chiarmenti:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrivi lu screenshot ncoppa
disco e stampa ancora JSON a stdout p'script. L'ID d''o screenshot veni 'e sòlitu
'a `local search-screen` o SQL ncoppa a tabella `screenshots`. Si Desktop torna
n'errure strutturatu comm'a `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, lu modo JSON preserva li campi `reason`, `hint` e
`screenshot_id` a stderr accussì l'agenti ponno ritentari un ID cchiù vecchiu
o signalari lu blocco esatto. Validati li nisciute riescite cu `file PATH`
primma 'e passarli ê strumenti 'e vistione.

## Esempiu travagliatu: ciclu 'e agenti nna Python

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

## Gistiune 'e limite 'e vilucità

Mimorie: 120/ura. Cummersazzioni: 25/ura. Creazzioni nna lotti: 15/ura.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suggerimenti

* Usa `--profile <name>` si lu tò agente gestisce tanti cunti Omi. Ogni prufilu
  àvi e so credenziali e a so base API.
* Usa `--api-base http://localhost:8080` p'test backend lucali.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` p'sustituiri e mpustazzioni
  de l'API lucale Desktop d''o prufilu pe na esecuzzione.
* Usa `--verbose` p'debug — reggistra `METHOD path → status (Ns)` a stderr
  senza affittari stdout, cussì lu modo JSON resta vàlitu.
* P'pipeari cuntinutu nna na cummersazzione, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
