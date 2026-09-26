# omi-cli per l'agenti

> Guida pratica per l'assistenti guidati da LLM (Claude Code, Cursor, i vostri bots).

## Perchè a CLI hè amichevule per l'agenti

* **Contrattu JSON stabile.** `--json` emette un documentu JSON validu nant'à
  stdout è *solu* un documentu JSON — nisciunu messaghju di prugressu, nisciunu
  spinner. L'errore vanu nant'à stderr cum'è `{"error": "...", "detail": "..."}`.
* **Codici di surtita stabili.** `0` bè / `1` usu / `2` autenticazione / `3`
  servitore / `4` limitatu da u ritimu / `5` micca truvatu. L'agenti ponu
  ramificà nant'à issi codici senza analizà l'errore in lingua naturale.
* **Nisciuna dumanda interattiva in i cuntesti headless.** Passate `--yes` (o
  `-y`) à i cumandi distruttivi; passate `--api-key` o definite `OMI_API_KEY`
  per francà a cunnessione interattiva.
* **Cumportamentu di riprova tollerante.** `429` è `5xx` sò riprovati cù un
  ritardu crescenu nanzu d'apparè.

## Autenticazione (una volta, da l'umanu)

L'utilizatore hà da ottene una chjave API dev da l'applicazione web Omi
(`https://app.omi.me` → Developer → API Keys) è po:

```bash
omi auth login                          # incollamentu interattivu; a chjave ùn entre micca in a storia di u shell
# o
export OMI_API_KEY=omi_dev_...          # efimeru, adattatu à i cuntinitori
```

## E cinque cose chì l'agenti facenu u più

### 1. Leghje e memorie

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Creà una memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leghje e conversazioni

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leghje l'elementi d'azione aperti

```bash
omi action-item list --json --open
```

### 5. Marcà un elementu d'azione cum'è fattu

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop Locale

Quandu Omi Desktop espone a so API locale, l'agenti ponu interrogà a storia di
schermu nant'à u dispusitivu, i riassunti, SQL è e taschene senza impiegà l'API
dev di u nuvulu:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, per e sessioni efimere:
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

Solu cumpletate o squassate e taschene quandu l'utilizatore u dumanda
chjaramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scrive a cattura di schermu
nant'à u discu è stampa sempre JSON nant'à stdout per i scripts. L'ID di a
cattura vene di solitu da `local search-screen` o da SQL nant'à a tavula
`screenshots`. S'è Desktop rende un fallimentu strutturatu cum'è
`screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`,
u modu JSON priserva i campi `reason`, `hint` è `screenshot_id` nant'à stderr
cusì chì l'agenti possinu riprovà cù un ID più vechju o segnalà u bloccu
esattu. Validate e surtite riesciute cù `file PATH` nanzu di passà le à
strumenti di visione.

## Esempiu cumpletu: ciclu d'agente in Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca a CLI omi in modu JSON, alzendu nant'à i codici di surtita micca riesciuti."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # A CLI stampa l'errore strutturati nant'à stderr in modu JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leghje tutti l'elementi d'azione aperti è marcà cum'è fatti quelli più vechji di 30 ghjorni.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gistione di e limite di ritimu

Memorie: 120/ora. Conversazioni: 25/ora. Creazioni in lottu: 15/ora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limitatu da u ritimu
    err = json.loads(result.stderr)
    # err["detail"] s'assumiglia à: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cunsiglii

* Impiegate `--profile <name>` s'è u vostru agente gestisce parechji conti Omi.
  Ogni profilu hà a so propria credenziale è basa d'API.
* Impiegate `--api-base http://localhost:8080` per pruvà u backend locale.
* Impiegate `OMI_LOCAL_API_URL` è `OMI_LOCAL_TOKEN` per annullà i parametri di
  l'API Desktop Locale di u profilu per una esecuzione.
* Impiegate `--verbose` per u debug — scrive `METHOD path → status (Ns)` nant'à
  stderr senza affettà stdout, dunque u modu JSON resta validu.
* Per canalizà cuntenutu versu una conversazione, impiegate `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
