# omi-cli per a agents

> Guia pràctica per a harness guiats per LLM (Claude Code, Cursor, els vostres propis bots).

## Per què la CLI és amigable per a agents

* **Contracte JSON estable.** `--json` emet un document JSON vàlid a stdout i
  *només* un document JSON — sense missatges de progrés, sense spinners. Els errors
  van a stderr com `{"error": "...", "detail": "..."}`.
* **Codis de sortida estables.** `0` ok / `1` ús / `2` auth / `3` servidor /
  `4` límit de velocitat / `5` no trobat. Els agents poden ramificar en aquests
  sense analitzar errors en llenguatge natural.
* **Sense prompts interactius en contextos headless.** Passa `--yes` (o `-y`) a
  comandes destructives; passa `--api-key` o estableix `OMI_API_KEY` per saltar
  el login interactiu.
* **Comportament de reintents perdonador.** `429` i `5xx` es reintenten amb
  backoff abans de sortir a la superfície.

## Auth (una vegada, per l'humà)

L'usuari obté una clau dev API de l'aplicació web Omi
(`https://app.omi.me` → Developer → API Keys) i o bé:

```bash
omi auth login                          # enganxada interactiva; la clau no queda a l'historial de la shell
# o
export OMI_API_KEY=omi_dev_...          # efímera, ideal per a contenidors
```

## Les cinc coses que els agents fan més

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

### 4. Llegir punts d'acció oberts

```bash
omi action-item list --json --open
```

### 5. Marcar un punt d'acció com a fet

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Quan Omi Desktop exposa la seva API local, els agents poden consultar l'historial
de pantalla del dispositiu, recaps, SQL i tasques sense usar la API dev del núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, per a sessions efímeres:
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

Completa o elimina tasques només quan l'usuari ho demana clarament:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escriu la captura de pantalla
al disc i encara imprimeix JSON a stdout per a scripts. L'ID de captura sol venir
de `local search-screen` o SQL sobre la taula `screenshots`. Si Desktop retorna
un error estructurat com `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, el mode JSON preserva els camps `reason`, `hint` i
`screenshot_id` a stderr perquè els agents puguin reintentar un ID més antic o
informar del bloqueig exacte. Valida les sortides reeixides amb `file PATH` abans
de passar-les a eines de visió.

## Exemple treballat: bucle d'agent en Python

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

## Gestió dels límits de velocitat

Memòries: 120/h. Converses: 25/h. Creacions en lot: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consells

* Usa `--profile <name>` si el teu agent gestiona diversos comptes Omi. Cada perfil
  té les seves pròpies credencials i base API.
* Usa `--api-base http://localhost:8080` per a proves de backend locals.
* Usa `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` per substituir els ajustos de la API
  local de Desktop del perfil per a una execució.
* Usa `--verbose` per depurar — registra `METHOD path → status (Ns)` a stderr
  sense afectar stdout, de manera que el mode JSON continua sent vàlid.
* Per fer pipe de contingut a una conversa, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
