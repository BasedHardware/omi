# omi-cli para agentes

> Guía práctica para entornos impulsados por LLMs (Claude Code, Cursor, tus propios bots).

## Por qué la CLI es amigable con los agentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a stdout y
  *solo* un documento JSON — sin mensajes de progreso, sin spinners. Los errores van a
  stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate
  limited / `5` not found. Los agentes pueden derivar lógica a partir de esto sin tener que procesar
  errores en lenguaje natural.
* **Sin prompts interactivos en contextos headless.** Pasa `--yes` (o `-y`) a los
  comandos destructivos; pasa `--api-key` o configura `OMI_API_KEY` para omitir el
  inicio de sesión interactivo.
* **Comportamiento de reintento tolerante.** `429` y `5xx` se reintentan con backoff
  antes de aparecer.

## Autenticación (una vez, por el humano)

El usuario obtiene una clave de API de desarrollo en la aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) y puede elegir entre:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Las cinco cosas que más hacen los agentes

### 1. Leer recuerdos

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear un recuerdo

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Leer conversaciones

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leer elementos de acción abiertos

```bash
omi action-item list --json --open
```

### 5. Marcar un elemento de acción como terminado

```bash
omi action-item complete --json a1b2c3d4
```

## API Local de Escritorio

Cuando Omi Desktop expone su API local, los agentes pueden consultar el historial
de pantalla en el dispositivo, resúmenes, SQL y tareas sin usar la API de desarrollo en la nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Solo completa o elimina tareas cuando el usuario lo solicite claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura de pantalla en
el disco y aún imprime JSON a stdout para los scripts. El ID de la captura normalmente
proviene de `local search-screen` o de SQL sobre la tabla `screenshots`. Si Desktop
devuelve un error estructurado como `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, el modo JSON conserva los campos `reason`, `hint`,
y `screenshot_id` en stderr para que los agentes puedan reintentar un ID anterior o informar del
bloqueador exacto. Valida que las salidas sean correctas con `file PATH` antes de pasarlas
a herramientas de visión.

## Ejemplo resuelto: Bucle de agente en Python

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

## Manejo de límites de tasa

Recuerdos: 120/hr. Conversaciones: 25/hr. Creación en lote: 15/hr.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Utiliza `--profile <name>` si tu agente maneja múltiples cuentas de Omi. Cada
  perfil tiene su propia credencial y base de API.
* Utiliza `--api-base http://localhost:8080` para pruebas del backend local.
* Utiliza `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para anular la configuración de la
  API de escritorio local del perfil para una sola ejecución.
* Utiliza `--verbose` para depurar — registra `METHOD path → status (Ns)` a stderr
  sin afectar a stdout, por lo que el modo JSON se mantiene válido.
* Para canalizar contenido en una conversación, utiliza `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
