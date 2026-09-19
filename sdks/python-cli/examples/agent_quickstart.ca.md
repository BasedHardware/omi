# omi-cli per a agents

> Guia pràctica per a entorns controlats per LLM (Claude Code, Cursor, els vostres propis bots).

## Per què el CLI és amigable amb els agents

* **Contracte JSON estable.** `--json` emet un document JSON vàlid cap a stdout i *només* aquest document — sense missatges de progrés ni spinners. Els errors s'escriuen a stderr com `{"error": "...", "detail": "..."}`.
* **Codis de sortida estables.** `0` ok / `1` error d'ús / `2` error de permisos / `3` error del servidor / `4` límit de taxa / `5` no trobat. Els agents poden ramificar-se en aquests codis sense analitzar el llenguatge natural als missatges d'error.
* **Sense avisos interactius en contextos headless.** Passeu `--yes` (o `-y`) per a ordres destructives; passeu `--api-key` o establiu `OMI_API_KEY` per ometre l'inici de sessió interactiu.
* **Lògica de reintents tolerant.** Els codis `429` i `5xx` es reintenten amb backoff exponencial abans de ser notificats.

## Autenticació (un cop, per part del humà)

L'usuari obté una clau d'API de desenvolupador de l'aplicació web d'Omi (`https://app.omi.me` → Developer → API Keys) i executa una de les opcions:

```bash
omi auth login                          # enganxament interactiu; la clau no va a l'historial de l'intèrpret d'ordres
# oder / ou / ili / or / ή / veya / või / o / ale /
export OMI_API_KEY=omi_dev_...          # temporal, compatible amb contenidors
```

## Les cinc coses que els agents fan més

### 1. Llegir records

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

### 4. Llegir elements d'acció oberts

```bash
omi action-item list --json --open
```

### 5. Marcar un element d'acció com a completat

```bash
omi action-item complete --json a1b2c3d4
```

## API local d'escriptori

Quan Omi Desktop exposa la seva API local, els agents poden consultar l'historial de pantalla del dispositiu, els resums, SQL i les tasques sense usar l'API dev del núvol:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# temporal, compatible amb contenidors:
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

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` desa la captura de pantalla al disc i segueix escrivint JSON a stdout per a scripts. Els ID de captura de pantalla provenen normalment de `local search-screen` o de SQL a la taula `screenshots`. Si Desktop retorna un error estructurat com `screenshot_pending`, `screenshot_file_missing` o `screenshot_chunk_corrupted`, el mode JSON preserva els camps `reason`, `hint` i `screenshot_id` a stderr perquè els agents puguin reintentar amb un ID més antic o informar de l'obstacle exacte. Verifiqueu els resultats satisfactoris amb `file PATH` abans de passar-los a les eines de visió.

## Exemple pràctic: bucle d'agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Executar el CLI d'omi en mode JSON i llençar una excepció en codis de sortida incorrectes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # El CLI escriu errors estructurats a stderr en mode JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi ha sortit amb el codi {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Llegir tots els elements d'acció oberts i marcar com a completats els de més de 30 dies.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestió de límits de taxa

Records: 120/hora. Converses: 25/hora. Creació per lots: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límit de taxa assolit
    err = json.loads(result.stderr)
    # err["detail"] sembla: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consells

* Useu `--profile <nom>` si el vostre agent gestiona diversos comptes d'Omi. Cada perfil té les seves pròpies credencials i base d'API.
* Useu `--api-base http://localhost:8080` per a les proves de backend local.
* Useu `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` per substituir la configuració d'API d'escriptori del perfil per a una sola execució.
* Useu `--verbose` per a la depuració — registra `METHOD path → status (Ns)` a stderr sense afectar stdout, de manera que el mode JSON segueix sent vàlid.
* Per canalitzar contingut a una conversa, useu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
