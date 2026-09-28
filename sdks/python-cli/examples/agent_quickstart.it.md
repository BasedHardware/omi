# omi-cli per agenti

> Guida pratica per ambienti guidati da LLM (Claude Code, Cursor, i vostri bot).

## Perché la CLI è adatta agli agenti

* **Contratto JSON stabile.** `--json` scrive su stdout un documento JSON valido e
  *solo* un documento JSON — nessun messaggio di avanzamento, nessuno spinner. Gli
  errori vanno su stderr nella forma `{"error": "...", "detail": "..."}`.
* **Codici di uscita stabili.** `0` ok / `1` errore di utilizzo / `2` autenticazione /
  `3` errore del server / `4` limite di richieste superato (rate limited) / `5` non
  trovato. Gli agenti possono decidere come procedere in base a questi codici senza
  interpretare messaggi di errore in linguaggio naturale.
* **Nessun prompt interattivo in contesti headless.** Passate `--yes` (o `-y`) ai
  comandi distruttivi; passate `--api-key` o impostate `OMI_API_KEY` per saltare
  l'accesso interattivo.
* **Nuovi tentativi automatici.** Le risposte `429` e `5xx` vengono ritentate con
  backoff prima di restituire l'errore.

## Autenticazione (una tantum, a cura dell'utente)

L'utente ottiene una chiave API sviluppatore dall'app web di Omi
(`https://app.omi.me` → Developer → API Keys) e poi sceglie una delle due opzioni:

```bash
omi auth login                          # inserimento interattivo; la chiave non finisce nella cronologia della shell
# oppure
export OMI_API_KEY=omi_dev_...          # effimera, adatta ai container
```

## Le cinque operazioni più frequenti degli agenti

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

### 5. Segnare un'attività come completata

```bash
omi action-item complete --json a1b2c3d4
```

## API locale di Desktop

Quando Omi Desktop espone la sua API locale, gli agenti possono interrogare la
cronologia dello schermo sul dispositivo, i riepiloghi, SQL e le attività senza
usare l'API cloud per sviluppatori:

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

Completate o eliminate attività solo quando l'utente lo chiede esplicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive lo screenshot su disco
e stampa comunque JSON su stdout per gli script. L'ID dello screenshot di solito
proviene da `local search-screen` o da una query SQL sulla tabella `screenshots`.
Se Desktop restituisce un errore strutturato come `screenshot_pending`,
`screenshot_file_missing` o `screenshot_chunk_corrupted`, la modalità JSON
conserva su stderr i campi `reason`, `hint` e `screenshot_id`, così gli agenti
possono riprovare con un ID più vecchio o segnalare l'ostacolo esatto. Verificate
gli output riusciti con `file PATH` prima di passarli agli strumenti di visione.

## Esempio pratico: ciclo di un agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI omi in modalità JSON, sollevando un'eccezione se il codice di uscita indica un errore."""
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

# Legge tutte le attività aperte e segna come completate quelle più vecchie di 30 giorni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestire i limiti di richieste (rate limit)

Ricordi: 120/ora. Conversazioni: 25/ora. Creazioni in batch: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite di richieste superato
    err = json.loads(result.stderr)
    # err["detail"] ha questa forma: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Suggerimenti

* Usate `--profile <nome>` se il vostro agente gestisce più account Omi. Ogni
  profilo ha le proprie credenziali e il proprio URL base dell'API.
* Usate `--api-base http://localhost:8080` per i test con un backend locale.
* Usate `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` per sovrascrivere, per una sola
  esecuzione, le impostazioni dell'API Desktop salvate nel profilo.
* Usate `--verbose` per il debug — registra `METHOD path → status (Ns)` su stderr
  senza toccare stdout, così la modalità JSON resta valida.
* Per inviare contenuto a una conversazione tramite pipe, usate `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
