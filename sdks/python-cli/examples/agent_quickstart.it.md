# omi-cli per agenti

> Guida pratica per ambienti basati su LLM (Claude Code, Cursor, i tuoi bot personalizzati).

## Perché la CLI è ideale per gli agenti

* **Contratto JSON stabile.** `--json` emette un documento JSON valido su `stdout` e
  *solo* un documento JSON: nessun messaggio di avanzamento o indicatore di caricamento. Gli errori vengono inviati su
  `stderr` come `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` successo / `1` errore di utilizzo / `2` autenticazione / `3` server / `4` limite
  di frequenza raggiunto (rate limit) / `5` non trovato. Gli agenti possono gestire i rami in base a questi codici senza dover analizzare
  gli errori in linguaggio naturale.
* **Nessuna richiesta interattiva in contesti headless.** Passa `--yes` (o `-y`) per i
  comandi distruttivi; passa `--api-key` o imposta `OMI_API_KEY` per saltare
  il login interattivo.
* **Comportamento di ripetizione resiliente.** Gli errori `429` e `5xx` vengono ritentati con backoff esponenziale
  prima di essere restituiti.

## Autenticazione (una tantum, eseguita dall'utente umano)

L'utente ottiene una chiave API sviluppatore dalla web app di Omi
(`https://app.omi.me` → Developer → API Keys) ed esegue una delle due opzioni:

```bash
omi auth login                          # inserimento interattivo; la chiave non rimane nella cronologia della shell
# oppure
export OMI_API_KEY=omi_dev_...          # effimero, ideale per container
```

## Le cinque azioni più comuni per gli agenti

### 1. Leggere i ricordi (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare un ricordo

```bash
omi memory create --json "L'utente preferisce la modalità scura" --category lifestyle
```

### 3. Leggere le conversazioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggere gli elementi d'azione aperti

```bash
omi action-item list --json --open
```

### 5. Contrassegnare un elemento d'azione come completato

```bash
omi action-item complete --json a1b2c3d4
```

## API locale di Desktop

Quando Omi Desktop espone la propria API locale, gli agenti possono interrogare la cronologia
dello schermo sul dispositivo, riepiloghi, SQL e attività senza utilizzare l'API sviluppatore cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oppure per sessioni effimere:
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

Completa o elimina le attività solo quando l'utente lo richiede esplicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` salva lo screenshot su disco e
continua a stampare JSON su `stdout` per gli script. L'ID dello screenshot proviene solitamente
da `local search-screen` o da una query SQL sulla tabella `screenshots`. Se Desktop
restituisce un errore strutturato come `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, la modalità JSON mantiene i campi `reason`, `hint` e
`screenshot_id` su `stderr` in modo che gli agenti possano ritentare con un ID precedente o segnalare
il motivo esatto del blocco. Convalida gli output riusciti con `file PATH` prima di passarli
agli strumenti di visione artificiale.

## Esempio pratico: ciclo dell'agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI di omi in modalità JSON, sollevando un'eccezione su codici di uscita diversi da zero."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI stampa errori strutturati su stderr in modalità JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi è terminato con codice {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legge tutti gli elementi d'azione aperti e completa quelli con più di 30 giorni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestione dei limiti di frequenza (rate limits)

Ricordi: 120/ora. Conversazioni: 25/ora. Creazioni in batch: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite di frequenza raggiunto
    err = json.loads(result.stderr)
    # err["detail"] è nel formato: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suggerimenti

* Usa `--profile <nome>` se il tuo agente gestisce più account Omi. Ciascun
  profilo mantiene le proprie credenziali e l'URL di base dell'API.
* Usa `--api-base http://localhost:8080` per test con backend locali.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere la configurazione dell'API Desktop locale
  del profilo per una singola esecuzione.
* Usa `--verbose` per il debug: registra `METHOD path status (Ns)` su `stderr`
  senza sporcare `stdout`, preservando la validità del flusso JSON.
* Per inviare contenuti a una conversazione tramite pipe, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
