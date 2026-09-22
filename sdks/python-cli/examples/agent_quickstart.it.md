# omi-cli per agenti

> Guida pratica per framework guidati da LLM (Claude Code, Cursor, bot personalizzati).

## Perché la CLI è ideale per gli agenti

* **Contratto JSON stabile.** `--json` emette un documento JSON valido su stdout e
  *soltanto* un documento JSON — nessun messaggio di avanzamento, nessun indicatore di caricamento (spinner). Gli errori vengono inviati su stderr sotto forma di `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` ok / `1` utilizzo errato / `2` autenticazione / `3` server / `4` limite di richieste raggiunto (rate limit) / `5` non trovato. Gli agenti possono creare rami condizionali su questi codici senza dover analizzare messaggi di errore in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passa `--yes` (o `-y`) per
  i comandi distruttivi; passa `--api-key` o imposta `OMI_API_KEY` per saltare
  il login interattivo.
* **Comportamento di retry tollerante.** Gli errori `429` e `5xx` vengono ritentati
  con backoff prima di essere sollevati.

## Autenticazione (singola, eseguita dall'utente umano)

L'utente ottiene una chiave API sviluppatore dall'applicazione web Omi
(`https://app.omi.me` → Developer → API Keys) e sceglie una delle opzioni:

```bash
omi auth login                          # incolla interattivo; la chiave non compare nella cronologia della shell
# oppure
export OMI_API_KEY=omi_dev_...          # effimero, ideale per container
```

## Le cinque operazioni più frequenti per gli agenti

### 1. Leggere i ricordi (memories)

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

### 4. Leggere gli elementi d'azione aperti

```bash
omi action-item list --json --open
```

### 5. Contrassegnare un elemento d'azione come completato

```bash
omi action-item complete --json a1b2c3d4
```

## API locale Desktop

Quando Omi Desktop espone la propria API locale, gli agenti possono interrogare la cronologia
dello schermo sul dispositivo, i riepiloghi, SQL e le attività senza utilizzare l'API cloud sviluppatore:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oppure, per sessioni effimere:
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

Completa o elimina le attività soltanto quando l'utente lo richiede esplicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive lo screenshot su
disco e continua a stampare JSON su stdout per gli script. L'ID dello screenshot proviene
solitamente da `local search-screen` o da una query SQL sulla tabella `screenshots`. Se Desktop
restituisce un errore strutturato come `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, la modalità JSON preserva i campi `reason`, `hint` e
`screenshot_id` su stderr, consentendo agli agenti di ritentare con un ID precedente o di segnalare il
blocco esatto. Verifica i file prodotti con `file PATH` prima di passarli agli strumenti di visione.

## Esempio pratico: ciclo per agenti Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI omi in modalità JSON, sollevando un'eccezione sui codici di uscita non nulli."""
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
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legge tutti gli elementi d'azione aperti e contrassegna come completati quelli più vecchi di 30 giorni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestione dei limiti di frequenza (rate limits)

Ricordi: 120/ora. Conversazioni: 25/ora. Creazioni in blocco: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] si presenta come: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consigli utili

* Usa `--profile <nome>` se il tuo agente gestisce più account Omi. Ogni
  profilo possiede le proprie credenziali e la propria base API.
* Usa `--api-base http://localhost:8080` per eseguire test con un backend locale.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere le impostazioni
  dell'API Desktop del profilo per una singola esecuzione.
* Usa `--verbose` per il debugging — registra `METHOD path → status (Ns)` su stderr
  senza influire su stdout, mantenendo valido l'output JSON.
* Per inviare contenuti tramite pipe in una conversazione, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
