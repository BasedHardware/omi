# omi-cli per a agents d'IA

> Guia pràctica per a entorns impulsats per LLM (Claude Code, Cursor, els vostres propis bots).

## Per què la CLI és amigable per als agents

* **Contracte JSON estable.** L'indicador `--json` emet un document JSON vàlid a stdout i
  *únicament* un document JSON — sense missatges de progrés ni indicadors de càrrega. Els
  errors s'envien a stderr com a `{"error": "...", "detail": "..."}`.
* **Codis de sortida estables.** `0` correcte / `1` error d'ús / `2` autenticació / `3` servidor /
  `4` límit de freqüència superat / `5` no trobat. Els agents poden ramificar la seva lògica
  directament sense analitzar text en llenguatge natural.
* **Sense sol·licituds interactives en contextos headless.** Passeu `--yes` (o `-y`) per a ordres
  destructives; passeu `--api-key` o configureu la variable `OMI_API_KEY` per ometre l'inici de sessió
  interactiu.
* **Comportament de reintent indulgent.** Els errors `429` i `5xx` es reintenten automàticament amb
  espera exponencial abans de manifestar-se.

## Autenticació (única, per l'humà)

L'usuari obté una clau API de desenvolupador des de l'aplicació web d'Omi
(`https://app.omi.me` → Developer → API Keys) i fa una d'aquestes opcions:

```bash
omi auth login                          # enganxament interactiu; la clau no es guarda a l'historial del shell
# o
export OMI_API_KEY=omi_dev_...          # efímer, apte per a contenidors
```

## Les cinc accions que els agents fan més sovint

### 1. Llegir memòries

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear una memòria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Llegir converses

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Llegir tasques pendents

```bash
omi action-item list --json --open
```

### 5. Marcar una tasca com a completada

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Quan Omi Desktop exposa la seva API local, els agents poden consultar l'historial de pantalla
del dispositiu, resums, dades SQL i tasques sense utilitzar l'API de desenvolupador al núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o per a sessions efímeres:
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

Completeu o elimineu tasques només quan l'usuari ho sol·liciti de manera explícita:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

L'ordre `omi local screenshot SCREENSHOT_ID --output PATH` desa la captura de pantalla al disc
i continua imprimint JSON a stdout per a l'ús en scripts. L'identificador de captura sol provenir
de `local search-screen` o d'una consulta SQL sobre la taula `screenshots`. Si Desktop retorna un
error estructurat com `screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`,
el mode JSON conserva els camps `reason`, `hint` i `screenshot_id` a stderr perquè els agents puguin
provar un ID anterior o notificar l'obstacle exacte. Valideu les sortides correctes amb `file PATH`
abans de passar-les a eines de visió per computador.

## Exemple pràctic: bucle d'agent en Python

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

## Gestió dels límits de freqüència (Rate Limits)

Memòries: 120/hora. Converses: 25/hora. Creacions per lots: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consells

* Utilitzeu `--profile <name>` si el vostre agent gestiona diversos comptes d'Omi. Cada
  perfil té les seves pròpies credencials i URL base d'API.
* Utilitzeu `--api-base http://localhost:8080` per a proves locals del backend.
* Utilitzeu `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` per substituir la configuració local de l'API
  de Desktop del perfil per a una única execució.
* Utilitzeu `--verbose` per a la depuració — registra `METHOD path → status (Ns)` a stderr sense
  afectar stdout, de manera que el mode JSON continua sent vàlid.
* Per canalitzar contingut cap a una conversa, utilitzeu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
