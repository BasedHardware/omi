# omi-cli per a agents

> Guia pràctica per a entorns basats en models LLM (Claude Code, Cursor, els vostres propis bots).

## Per què la CLI és adequada per a agents

* **Contracte JSON estable.** La bandera `--json` emet un document JSON vàlid a stdout i *únicament* un document JSON — sense missatges de progrés, sense indicadors de càrrega. Els errors van a stderr com `{"error": "...", "detail": "..."}`.
* **Codis de sortida estables (exit codes).** `0` correcte / `1` error d'ús / `2` error d'autenticació / `3` error de servidor / `4` límit de peticions superat / `5` no trobat. Els agents poden prendre decisions a partir d'aquests codis sense analitzar missatges en llenguatge natural.
* **Sense preguntes interactives en mode headless.** Passeu `--yes` (o `-y`) per a ordres destructives; passeu `--api-key` o definiu la variable d'entorn `OMI_API_KEY` per ometre l'inici de sessió interactiu.
* **Comportament de reintent flexible.** Els codis d'error `429` i `5xx` es reintenten automàticament amb un retard exponencial (backoff) abans de mostrar l'error.

## Autenticació (única vegada, realitzada per una persona)

L'usuari obté una clau API de desenvolupador des de l'aplicació web d'Omi
(`https://app.omi.me` → Developer → API Keys) i executa una de les següents opcions:

```bash
omi auth login                          # enganxament interactiu; la clau no es desa a l'historial del terminal
# o bé
export OMI_API_KEY=omi_dev_...          # efímer, ideal per a contenidors
```

## Les cinc accions més freqüents dels agents

### 1. Llegir records (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear un record

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Llegir converses

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Llegir tasques pendents (action items)

```bash
omi action-item list --json --open
```

### 5. Marcar una tasca com a completada

```bash
omi action-item complete --json a1b2c3d4
```

## API d'escriptori local (Local Desktop API)

Quan Omi Desktop habilita la seva API local, els agents poden consultar l'historial de pantalla del dispositiu, resums, SQL i tasques sense utilitzar l'API al núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o bé per a sessions efímeres:
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

Completeu o elimineu tasques només quan l'usuari ho demani explícitament:

Completeu o elimineu tasques només quan l'usuari ho demani explícitament:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escriu la captura de pantalla al disc i continua imprimint JSON a stdout per als scripts. L'ID de captura normalment prové de `local search-screen` o d'una consulta SQL sobre la taula `screenshots`. Si Desktop retorna un error estructurat com `screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`, el mode JSON preserva els camps `reason`, `hint` i `screenshot_id` a stderr perquè els agents puguin reintentar amb un ID més antic o informar del bloqueig exacte. Valideu les sortides correctes amb `file PATH` abans de passar-les a eines de visió.

## Exemple pràctic: bucle d'agent Python

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

## Gestió de límits de velocitat (Handling rate limits)

Memòries: 120/hora. Converses: 25/hora. Creacions per lots: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consells útils (Tips)

* Utilitzeu `--profile <nom>` si el vostre agent gestiona diversos comptes Omi. Cada perfil té les seves pròpies credencials i URL base d'API.
* Utilitzeu `--api-base http://localhost:8080` per a proves amb el dorsal local.
* Utilitzeu `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` per anul·lar la configuració de Desktop API del perfil per a una sola execució.
* Utilitzeu `--verbose` per a la depuració: registra `METHOD path → status (Ns)` a stderr sense afectar stdout, mantenint vàlid el mode JSON.
* Per canalitzar contingut cap a una conversa mitjançant un conducte (pipe), utilitzeu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
