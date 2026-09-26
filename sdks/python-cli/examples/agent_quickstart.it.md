# omi-cli per agenti IA

> Guida pratica per ambienti guidati da LLM (Claude Code, Cursor o bot di automazione personalizzati).

## Perché la CLI è adatta agli agenti

* **Protocollo JSON stabile.** Il flag `--json` invia un singolo documento JSON valido a stdout e *solo* il documento JSON — senza messaggi di avanzamento o spinner. Gli errori vengono stampati su stderr come `{"error": "...", "detail": "..."}`.
* **Codici di uscita prevedibili.** `0` successo / `1` errore di utilizzo / `2` errore di autenticazione / `3` errore del server / `4` limite di frequenza superato (rate limited) / `5` risorsa non trovata. Gli agenti possono ramificare la logica direttamente sui codici di uscita senza dover interpretare il linguaggio naturale.
* **Non interattivo per impostazione predefinita in ambienti headless.** Passare `--yes` (o `-y`) per i comandi distruttivi; passare `--api-key` o impostare la variabile di ambiente `OMI_API_KEY` per saltare l'accesso interattivo.
* **Tentativi automatici integrati.** I codici di errore `429` e `5xx` vengono ritentati automaticamente con backoff prima di restituire l'errore al chiamante.

## Autenticazione (Una tantum, eseguita dall'utente umano)

L'utente ottiene una chiave API per sviluppatori dalla web app di Omi (`https://app.omi.me` → Developer → API Keys) ed esegue una delle due opzioni:

```bash
omi auth login                          # inserimento interattivo; la chiave non finisce nella cronologia della shell
# oppure
export OMI_API_KEY=omi_dev_...          # temporanea, adatta a container
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

### 4. Leggere le attività aperte

```bash
omi action-item list --json --open
```

### 5. Contrassegnare un'attività come completata

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API (API Desktop Locale)

Quando l'applicazione Omi Desktop espone l'API locale, gli agenti possono leggere la cronologia dello schermo, i riepiloghi giornalieri, il database SQL locale e le attività direttamente sul dispositivo senza effettuare chiamate all'API cloud:

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

Mutazioni locali (attività):

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

## Esempio pratico: Loop per agenti Python

```python
import json
import subprocess
import sys

def run_omi(*args: str) -> dict | list:
    """Esegue la CLI di omi in modalità JSON, sollevando un'eccezione sui codici di uscita diversi da zero."""
    cmd = ["omi", "--json", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # La CLI stampa errori strutturati su stderr in modalità JSON:
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"raw": result.stderr}
        raise RuntimeError(f"omi fallito (exit {result.returncode}): {err}")
    return json.loads(result.stdout)

# Legge tutte le attività aperte e contrassegna come completate quelle più vecchie di 30 giorni.
from datetime import datetime, timezone, timedelta

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = run_omi("action-item", "list", "--open")
for item in items:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        print(f"Completamento attività precedente: {item['id']} ({item['description']})")
        run_omi("action-item", "complete", item["id"])
```

## Gestione dei limiti di frequenza (Rate Limits)

```python
if result.returncode == 4:                             # limite di frequenza superato
    err = json.loads(result.stderr)
    # err["detail"] si presenta come: "Retry in 12s. ..."
    # La CLI di omi esegue già 3 tentativi internamente; se si riceve comunque
    # il codice 4, sospendere le chiamate per l'intervallo indicato.
```

Limiti di frequenza cloud correnti per le chiavi API dev:
* Lettura (GET): 120 richieste / min
* Scrittura (POST/PUT/DELETE): 25 richieste / min
* Ricerca semantica: 15 richieste / min

Limiti locali (tramite Desktop API): nessun limite artificiale; vincolato dalle prestazioni dell'hardware host.

## Suggerimenti

* Utilizzare `--profile <name>` se l'agente deve passare tra più account Omi (ad esempio test vs produzione). Le credenziali vengono memorizzate separatamente in `~/.config/omi/profiles/<name>.json`.
* Per i test unitari con server simulati (mock): passare `--api-base http://localhost:8080`.
* Non analizzare stdout in formato testo non strutturato — il layout è ottimizzato per la lettura umana e può cambiare tra le versioni. Utilizzare sempre `--json` negli script di automazione.
