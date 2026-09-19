# omi-cli per agenti

> Guida pratica per harness basati su LLM (Claude Code, Cursor, bot personalizzati).

## Perché la CLI è ideale per gli agenti

* **Contratto JSON stabile.** `--json` emette su stdout un documento JSON valido e *soltanto* un documento JSON — nessun messaggio di avanzamento, nessuno spinner. Gli errori vengono inviati su stderr come `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` ok / `1` errore di utilizzo / `2` autenticazione / `3` server / `4` limite di richieste (rate limited) / `5` non trovato. Gli agenti possono creare rami logici su questi codici senza dover analizzare messaggi di errore in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passa `--yes` (o `-y`) per i comandi distruttivi; passa `--api-key` o imposta `OMI_API_KEY` per saltare il login interattivo.
* **Comportamento di ripetizione resiliente.** Gli errori `429` e `5xx` vengono ritentati automaticamente con backoff prima di essere segnalati.

## Autenticazione (una sola volta, da parte dell'utente)

L'utente ottiene una chiave API per sviluppatori dalla web app di Omi (`https://app.omi.me` → Developer → API Keys) e sceglie una delle seguenti opzioni:

```bash
omi auth login                          # incolla interattivo; la chiave non rimane nella cronologia della shell
# oppure
export OMI_API_KEY=omi_dev_...          # effimero, ideale per container
```

## Le cinque operazioni più comuni eseguite dagli agenti

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

### 4. Leggere gli elementi di azione aperti

```bash
omi action-item list --json --open
```

### 5. Contrassegnare un elemento di azione come completato

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API locale

Quando Omi Desktop espone la propria API locale, gli agenti possono interrogare la cronologia dello schermo sul dispositivo, i riepiloghi, SQL e le attività senza utilizzare l'API cloud per sviluppatori:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oppure per sessioni temporanee:
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

`omi local screenshot SCREENSHOT_ID --output PATH` scrive lo screenshot su disco e continua a stampare JSON su stdout per gli script. L'ID dello screenshot proviene in genere da `local search-screen` o da una query SQL sulla tabella `screenshots`. Se Desktop restituisce un errore strutturato come `screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`, la modalità JSON conserva i campi `reason`, `hint` e `screenshot_id` su stderr, consentendo agli agenti di riprovare con un ID precedente o di segnalare l'esatto blocco. Verifica gli output corretti con `file PATH` prima di passarli agli strumenti di visione.

## Esempio pratico: ciclo agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI omi in modalità JSON, sollevando un'eccezione se il codice di uscita non è zero."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # In modalità JSON la CLI stampa errori strutturati su stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legge tutti gli elementi di azione aperti e contrassegna come completati quelli più vecchi di 30 giorni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestione dei limiti di frequenza

Ricordi: 120/ora. Conversazioni: 25/ora. Creazioni in batch: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite di frequenza raggiunto
    err = json.loads(result.stderr)
    # err["detail"] ha un formato simile a: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suggerimenti utili

* Usa `--profile <name>` se il tuo agente gestisce più account Omi. Ogni profilo ha le proprie credenziali e il proprio URL di base dell'API.
* Usa `--api-base http://localhost:8080` per i test locali del backend.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere le impostazioni della Desktop API locali del profilo per una singola esecuzione.
* Usa `--verbose` per il debug — registra `METHOD path → status (Ns)` su stderr senza influire su stdout, mantenendo valida la modalità JSON.
* Per inviare contenuti a una conversazione tramite pipe, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
