# omi-cli per agenti

> Guida pratica per workflow basati su LLM (Claude Code, Cursor, bot personalizzati).

## Perché la CLI è ideale per gli agenti

* **Contratto JSON stabile.** `--json` emette un documento JSON valido su stdout e
  *soltanto* un documento JSON — nessun messaggio di avanzamento, nessuno spinner. Gli errori
  vengono inviati a stderr come `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` ok / `1` errore d'uso / `2` autenticazione / `3` errore server /
  `4` limite di richieste / `5` non trovato. Gli agenti possono ramificare su questi codici
  senza dover analizzare errori in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passa `--yes` (o `-y`) per i comandi distruttivi;
  passa `--api-key` o imposta `OMI_API_KEY` per saltare il login interattivo.
* **Comportamento di ripetizione permissivo.** Gli errori `429` e `5xx` vengono ritentati
  con backoff prima di essere notificati.

## Autenticazione (una tantum, eseguita dall'utente umano)

L'utente ottiene una chiave API per sviluppatori dalla web app di Omi
(`https://app.omi.me` → Developer → API Keys) e sceglie una delle seguenti opzioni:

```bash
omi auth login                          # incolla interattivo; la chiave non finisce nella cronologia shell
# oppure
export OMI_API_KEY=omi_dev_...          # effimero, ideale per container
```

## Le cinque operazioni più frequenti per gli agenti

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

### 4. Leggere le azioni aperte

```bash
omi action-item list --json --open
```

### 5. Contrassegnare un'azione come completata

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Locale

Quando Omi Desktop espone la propria API locale, gli agenti possono interrogare cronologia dello schermo,
riepiloghi, SQL e attività sul dispositivo senza usare l'API cloud dev:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# oppure, per sessioni temporanee:
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

Completa o elimina attività solo quando l'utente lo richiede esplicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` salva lo screenshot su disco
e continua a stampare JSON su stdout per gli script. L'ID dello screenshot proviene di solito
da `local search-screen` o da una query SQL sulla tabella `screenshots`. Se Desktop
restituisce un errore strutturato come `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, la modalità JSON preserva i campi `reason`, `hint` e
`screenshot_id` su stderr, consentendo agli agenti di ritentare con un ID precedente o segnalare
l'esatto blocco. Verifica gli output riusciti con `file PATH` prima di passarli a strumenti di visione.

## Esempio pratico: ciclo agent in Python

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

## Gestione dei limiti di frequenza

Ricordi: 120/ora. Conversazioni: 25/ora. Creazioni in blocco: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consigli utili

* Usa `--profile <nome>` se il tuo agente gestisce più account Omi. Ciascun
  profilo possiede le proprie credenziali e il proprio base URL API.
* Usa `--api-base http://localhost:8080` per test con backend locali.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere le impostazioni Desktop API
  locali del profilo per una singola esecuzione.
* Usa `--verbose` per il debugging — registra `METHOD path → status (Ns)` su stderr
  senza alterare stdout, preservando la validità della modalità JSON.
* Per inviare contenuti in una conversazione tramite pipe, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
