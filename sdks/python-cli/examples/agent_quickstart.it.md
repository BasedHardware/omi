# omi-cli per agenti

> Guida pratica per harness guidati da LLM (Claude Code, Cursor, i tuoi bot).

## Perché la CLI è adatta agli agenti

* **Contratto JSON stabile.** `--json` emette su stdout un documento JSON valido e *solo* JSON — niente messaggi di avanzamento né spinner. Gli errori vanno a stderr come `{"error": "...", "detail": "..."}`.
* **Exit code stabili.** `0` ok / `1` uso / `2` auth / `3` server / `4` rate limited / `5` non trovato. Gli agenti possono diramare su questi senza analizzare errori in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passa `--yes` (o `-y`) ai comandi distruttivi; passa `--api-key` o imposta `OMI_API_KEY` per saltare il login interattivo.
* **Retry indulgente.** `429` e `5xx` vengono ritentati con backoff prima di emergere.

## Autenticazione (una tantum, da parte umana)

L'utente ottiene una dev API key dall'app web Omi
(`https://app.omi.me` → Developer → API Keys) e poi:

```bash
omi auth login                          # incolla interattivo; key non nella shell history
# # oppure
export OMI_API_KEY=omi_dev_...          # effimera, adatta ai container
```

## Le cinque cose che gli agenti fanno di più

### 1. Leggere le memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare una memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leggere le conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggere gli action item aperti

```bash
omi action-item list --json --open
```

### 5. Segnare un action item come completato

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop locale

Quando Omi Desktop espone la sua API locale, gli agenti possono interrogare
screen history, riepiloghi, SQL e task sul dispositivo senza usare la dev API cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # oppure, per sessioni effimere:
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

Completa o elimina i task solo quando l'utente lo chiede chiaramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive lo screenshot su
disco e stampa comunque JSON su stdout per gli script. L'ID screenshot di solito
arriva da `local search-screen` o da SQL sulla tabella `screenshots`. Se Desktop
restituisce un errore strutturato come `screenshot_pending`,
`screenshot_file_missing` o `screenshot_chunk_corrupted`, la modalità JSON
preserva `reason`, `hint` e `screenshot_id` su stderr così l'agente può riprovare
con un ID più vecchio o segnalare il blocco esatto. Valida gli output riusciti
con `file PATH` prima di passarli a strumenti di visione.

## Esempio svolto: loop agente Python

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

# Leggi tutti gli action item aperti e completa quelli più vecchi di 30 giorni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestione dei rate limit

Memories: 120/ora. Conversations: 25/ora. Creazioni batch: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] ha questa forma: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suggerimenti

* Usa `--profile <name>` se l'agente gestisce più account Omi. Ogni profilo
  ha credenziali e API base proprie.
* Usa `--api-base http://localhost:8080` per test del backend locale.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere le
  impostazioni Desktop API del profilo per una singola esecuzione.
* Usa `--verbose` per il debug — registra `METHOD path → status (Ns)` su stderr
  senza toccare stdout, quindi il JSON resta valido.
* Per fare piping di contenuti in una conversation, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
