# omi-cli para agentes

> Guía práctica para entornos controlados por LLM (Claude Code, Cursor o tus propios bots).

## Por qué el CLI es adecuado para agentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido en stdout y
  *solo* un documento JSON: no muestra mensajes de progreso ni spinners. Los
  errores van a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` correcto / `1` uso incorrecto / `2`
  autenticación / `3` servidor / `4` límite de solicitudes / `5` no encontrado.
  Los agentes pueden tomar decisiones con ellos sin analizar errores en lenguaje
  natural.
* **Sin prompts interactivos en contextos headless.** Pasa `--yes` (o `-y`) a
  los comandos destructivos; pasa `--api-key` o define `OMI_API_KEY` para omitir
  el inicio de sesión interactivo.
* **Reintentos tolerantes.** Los códigos `429` y `5xx` se reintentan con
  backoff antes de devolverse al usuario.

## Autenticación (una sola vez, por la persona usuaria)

La persona usuaria obtiene una clave API de desarrollo desde la aplicación web
de Omi (`https://app.omi.me` → Developer → API Keys) y usa una de estas
opciones:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Las cinco tareas que más hacen los agentes

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

### 4. Leer tareas abiertas

```bash
omi action-item list --json --open
```

### 5. Marcar una tarea como terminada

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cuando Omi Desktop expone su API local, los agentes pueden consultar el
historial de pantalla del dispositivo, resúmenes, SQL y tareas sin usar la API
de desarrollo en la nube:

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

Completa o elimina tareas solo cuando la persona usuaria lo solicite
claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura en disco
y también imprime JSON en stdout para los scripts. El ID de captura suele
provenir de `local search-screen` o de SQL sobre la tabla `screenshots`. Si
Desktop devuelve un fallo estructurado como `screenshot_pending`,
`screenshot_file_missing` o `screenshot_chunk_corrupted`, el modo JSON conserva
los campos `reason`, `hint` y `screenshot_id` en stderr para que el agente pueda
reintentar con un ID anterior o informar del bloqueo exacto. Valida las salidas
correctas con `file PATH` antes de pasarlas a herramientas de visión.

## Ejemplo completo: ciclo de un agente Python

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

## Cómo gestionar los límites de solicitudes

Recuerdos: 120 por hora. Conversaciones: 25 por hora. Creaciones por lotes: 15
por hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Usa `--profile <name>` si tu agente alterna entre varias cuentas de Omi. Cada
  perfil tiene sus propias credenciales y base de API.
* Usa `--api-base http://localhost:8080` para probar el backend local.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para sobrescribir la configuración
  de la API de Desktop del perfil en una sola ejecución.
* Usa `--verbose` para depurar: registra `METHOD path → status (Ns)` en stderr
  sin modificar stdout, por lo que el modo JSON sigue siendo válido.
* Para pasar contenido a una conversación, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
