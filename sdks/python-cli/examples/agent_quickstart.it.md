# omi-cli per agenti

> Guida pratica per ambienti guidati da LLM (Claude Code, Cursor, i tuoi bot).

## Perché la CLI è ideale per gli agenti

* **Contratto JSON stabile.** `--json` emette un documento JSON valido su stdout e
  *soltanto* un documento JSON — nessun messaggio di avanzamento, nessuno spinner. Gli errori vengono inviati su
  stderr come `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` ok / `1` errore di utilizzo / `2` autenticazione fallita / `3` errore del server / `4` limite
  di frequenza raggiunto (rate limited) / `5` non trovato. Gli agenti possono ramificare la logica su questi codici senza dover analizzare
  gli errori in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passa `--yes` (o `-y`) per i
  comandi distruttivi; passa `--api-key` o imposta `OMI_API_KEY` per saltare
  l'accesso interattivo.
* **Comportamento di ripetizione tollerante.** Gli errori `429` e `5xx` vengono ritentati automaticamente con backoff
  esponenziale prima di essere segnalati.

## Autenticazione (una sola volta, a cura dell'utente)

L'utente ottiene una chiave API per sviluppatori dalla web app di Omi
(`https://app.omi.me` → Developer → API Keys) e sceglie una delle seguenti opzioni:

```bash
omi auth login                          # incolla in modo interattivo; la chiave non finisce nella cronologia della shell
# oppure
export OMI_API_KEY=omi_dev_...          # effimero, ideale per container
```

## Le cinque azioni più frequenti per gli agenti

### 1. Leggere i ricordi

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creare un ricordo

```bash
omi memory create --json "L'utente preferisce il tema scuro" --category lifestyle
```

### 3. Leggere le conversazioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leggere le attività aperte

```bash
omi action-item list --json --open
```

### 5. Contrassegnare un'attività come completata

```bash
omi action-item complete --json a1b2c3d4
```

## API locale di Desktop

Quando Omi Desktop espone la sua API locale, gli agenti possono interrogare la cronologia
dello schermo sul dispositivo, i riepiloghi, le query SQL e le attività senza dover usare l'API cloud:

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

Completa o elimina le attività soltanto se l'utente lo richiede chiaramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` salva lo screenshot su disco
e restituisce comunque JSON su stdout per gli script. L'ID dello screenshot proviene in genere
da `local search-screen` o da query SQL sulla tabella `screenshots`. Se Desktop
restituisce un errore strutturato come `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, la modalità JSON conserva i campi `reason`, `hint` e
`screenshot_id` su stderr, consentendo agli agenti di riprovare con un ID precedente o segnalare
l'ostacolo esatto. Verifica gli output corretti con `file PATH` prima di passarli agli strumenti di visione.

## Esempio pratico: ciclo dell'agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Esegue la CLI di omi in modalità JSON, sollevando eccezione in caso di codice di uscita diverso da 0."""
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
        raise RuntimeError(f"omi è uscito con codice {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Legge tutte le attività aperte e contrassegna come completate quelle create più di 30 giorni fa.
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
if result.returncode == 4:                             # limite di frequenza raggiunto
    err = json.loads(result.stderr)
    # err["detail"] ha un formato del tipo: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consigli

* Usa `--profile <nome>` se il tuo agente gestisce più account Omi. Ogni
  profilo dispone delle proprie credenziali e della propria base API.
* Usa `--api-base http://localhost:8080` per eseguire test con un backend locale.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere le impostazioni
  locali dell'API Desktop del profilo per una singola esecuzione.
* Usa `--verbose` per il debug — registra `METHOD percorso → stato (Ns)` su stderr
  senza influire su stdout, mantenendo valido il formato JSON.
* Per inviare contenuti a una conversazione tramite pipe, usa `--text -`:
  ```bash
  cat appunti_riunione.md | omi conversation create --text - --text-source other_text
  ```
