# omi-cli per agenti

> Guida pratica per harness guidati da LLM (Claude Code, Cursor, i tuoi bot).

## Perché la CLI è adatta agli agenti

* **Contratto JSON stabile.** `--json` emette un documento JSON valido su stdout e
  *solo* un documento JSON — nessun messaggio di avanzamento, nessuno spinner. Gli errori vanno su
  stderr come `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate
  limited / `5` not found. Gli agenti possono creare ramificazioni in base a questi codici senza analizzare
  errori in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passa `--yes` (o `-y`) ai
  comandi distruttivi; passa `--api-key` o imposta `OMI_API_KEY` per saltare il
  login interattivo.
* **Comportamento di ripetizione tollerante.** `429` e `5xx` vengono ritentati con un backoff
  prima di essere mostrati.

## Autenticazione (una tantum, da parte dell'umano)

L'utente ottiene una chiave API di sviluppo nell'app web di Omi
(`https://app.omi.me` → Developer → API Keys) e sceglie tra:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Le cinque cose che gli agenti fanno più spesso

### 1. Leggere i ricordi

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare un ricordo

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leggere le conversazioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggere le azioni da completare (action items aperti)

```bash
omi action-item list --json --open
```

### 5. Segnare un'azione da completare (action item) come completata

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Locale

Quando Omi Desktop espone la sua API locale, gli agenti possono interrogare la cronologia
dello schermo sul dispositivo, i riepiloghi, SQL e le attività senza usare l'API cloud di sviluppo:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Completa o elimina le attività (task) solo quando l'utente lo richiede esplicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` salva lo screenshot su
disco e stampa comunque JSON su stdout per gli script. L'ID dello screenshot deriva
solitamente da `local search-screen` o da SQL sulla tabella `screenshots`. Se Desktop
restituisce un errore strutturato come `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, la modalità JSON conserva i campi `reason`, `hint`,
e `screenshot_id` su stderr affinché gli agenti possano riprovare con un ID meno recente o riportare il
blocco esatto. Verifica la validità degli output con `file PATH` prima di passarli
a strumenti di visione artificiale.

## Esempio svolto: Ciclo dell'agente in Python

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

## Gestione dei limiti di velocità (Rate limits)

Ricordi: 120/hr. Conversazioni: 25/hr. Creazioni in batch: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consigli utili

* Usa `--profile <name>` se il tuo agente gestisce più account Omi. Ogni
  profilo ha le proprie credenziali e la propria base API.
* Usa `--api-base http://localhost:8080` per testare il backend locale.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere le impostazioni locali del profilo
  dell'API Desktop per una singola esecuzione.
* Usa `--verbose` per il debugging — registra `METHOD path → status (Ns)` su stderr
  senza alterare stdout, cosicché la modalità JSON resti valida.
* Per indirizzare (pipe) il contenuto all'interno di una conversazione, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
