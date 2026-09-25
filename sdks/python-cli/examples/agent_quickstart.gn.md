# omi-cli agente kuérape guarã

> Pe guía práctika LLM oisãmbyhýva umi harness pe guarã (Claude Code, Cursor, nde bot teéva).

## Mba'érepa CLI iporã agente kuérape

* **JSON kontrátu estable.** `--json` omondo peteĩ JSON kuatia oikóva stdout-pe ha
  *upénte* peteĩ JSON kuatia — ndaipóri mensaje de progreso, ndaipóri spinner.
  Umi jejavy oho stderr-pe `{"error": "...", "detail": "..."}` ramo.
* **Código de salida estable.** `0` OK / `1` jeporu / `2` autenticación / `3`
  servidor / `4` límite de velocidad / `5` ndojejuhúi. Umi agente ikatu ojapo
  ramifikación ko'ã código rehe ndoanalisa'ỹi jejavy ñe'ẽme.
* **Ndaipóri pregunta interactiva contexto headless-pe.** Emondo `--yes` (térã
  `-y`) umi comando destructivo-pe; emondo `--api-key` térã emoĩ `OMI_API_KEY`
  emosarambívo pe login interactivo.
* **Retry ojejapóva heta jey.** `429` ha `5xx` ojejapo jey backoff ndive osẽ
  mboyve.

## Autenticación (peteĩ jey, yvypóra ojapóva)

Umi puruhára ohupyty peteĩ dev API llave Omi web app gui
(`https://app.omi.me` → Developer → API Keys) ha upéi:

```bash
omi auth login                          # ojepega interactivamente; llave ndoike shell historial-pe
# térã
export OMI_API_KEY=omi_dev_...          # efímero, contenedor pe guarã
```

## Umi po mba'e agente ojapovéva

### 1. Emoñe'ẽ umi memoria

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Emoheñói peteĩ memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Emoñe'ẽ umi conversación

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Emoñe'ẽ umi acción ojepe'áva abierto

```bash
omi action-item list --json --open
```

### 5. Emomarká peteĩ acción ojapopapáramo

```bash
omi action-item complete --json a1b2c3d4
```

## API Local Desktop

Omi Desktop ohechaukávo pe API local, umi agente ikatu oporandu pe pantalla
historial dispositivo-pe, umi recap, SQL ha umi tarea ndoiporúi pe cloud dev
API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# térã, sesión efímero pe guarã:
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

Ejapopa térã embogue tarea añónte puruhára ojeruréramo:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ohai pe screenshot disco-pe
ha omondo gueteri JSON stdout-pe script pe guarã. Pe screenshot ID umumente ou
`local search-screen` gui térã SQL `screenshots` tabla gui. Desktop omoĩramo
peteĩ fallo estructurado `screenshot_pending`, `screenshot_file_missing` térã
`screenshot_chunk_corrupted` ramo, pe JSON modo omoĩ umi campo `reason`, `hint`
ha `screenshot_id` stderr-pe, ani agente ikatu ojapo jey peteĩ ID tuja ndive
térã omombe'u exacto mba'épa oĩ. Ehechajey umi osẽ porãva `file PATH` ndive
emondóvo umi visión herramienta-pe.

## Ejemplo: Python agente bucle

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Ohenói omi CLI JSON modo-pe, omosẽ peteĩ error código de salida ndoikóiramo."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ohai umi error estructurado stderr-pe JSON modo-pe:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Emoñe'ẽ opaite acción abierto ha emomarká umi ohasava'ekue 30 ára ojapopapáramo.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Límite de velocidad rehegua

Memorias: 120/ara. Conversación: 25/ara. Grupo creación: 15/ara.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de velocidad
    err = json.loads(result.stderr)
    # err["detail"] ohechauka: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejo

* Eiporu `--profile <name>` nde agente oguerekóramo heta Omi cuenta. Peteĩteĩ
  perfil oguereko isãmbyhy ha API base.
* Eiporu `--api-base http://localhost:8080` pe local backend prueba pe guarã.
* Eiporu `OMI_LOCAL_API_URL` ha `OMI_LOCAL_TOKEN` emoambuévo pe perfil Desktop
  API configuración peteĩ ejecución pe guarã.
* Eiporu `--verbose` debug pe guarã — ohai `METHOD path → status (Ns)`
  stderr-pe ndomoambuéi stdout, upéva rupi pe JSON modo oiko porã jepi.
* Emondo contenido peteĩ conversación-pe, eiporu `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
