# omi-cli para agentes

> Guía práctica para entornos impulsados por LLM (Claude Code, Cursor, tus propios bots).

## Por qué el CLI es ideal para agentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a `stdout` y
  *únicamente* un documento JSON: sin mensajes de progreso ni indicadores de carga. Los errores se envían a
  `stderr` como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` correcto / `1` error de uso / `2` autenticación / `3` servidor / `4` límite
  de velocidad alcanzado (rate limited) / `5` no encontrado. Los agentes pueden bifurcar según estos códigos sin necesidad de analizar
  errores en lenguaje natural.
* **Sin solicitudes interactivas en contextos headless.** Pasa `--yes` (o `-y`) para
  comandos destructivos; pasa `--api-key` o define `OMI_API_KEY` para omitir
  el inicio de sesión interactivo.
* **Comportamiento de reintento tolerante.** Los errores `429` y `5xx` se reintentan con retroceso exponencial
  antes de mostrarse.

## Autenticación (única vez, realizada por el humano)

El usuario obtiene una clave de API de desarrollador desde la aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) y realiza cualquiera de las dos opciones:

```bash
omi auth login                          # pegado interactivo; la clave no queda en el historial de la shell
# o
export OMI_API_KEY=omi_dev_...          # efímero, ideal para contenedores
```

## Las cinco acciones más comunes para agentes

### 1. Leer recuerdos (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear un recuerdo

```bash
omi memory create --json "El usuario prefiere el modo oscuro" --category lifestyle
```

### 3. Leer conversaciones

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Leer elementos de acción pendientes

```bash
omi action-item list --json --open
```

### 5. Marcar un elemento de acción como completado

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cuando Omi Desktop expone su API local, los agentes pueden consultar el historial
de pantalla en el dispositivo, resúmenes, SQL y tareas sin utilizar la API de desarrollador en la nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o para sesiones efímeras:
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

Solo completa o elimina tareas cuando el usuario lo solicite expresamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` guarda la captura de pantalla en el
disco y continúa imprimiendo JSON en `stdout` para scripts. El ID de la captura suele provenir
de `local search-screen` o de una consulta SQL sobre la tabla `screenshots`. Si Desktop
devuelve un error estructurado como `screenshot_pending`, `screenshot_file_missing`
o `screenshot_chunk_corrupted`, el modo JSON preserva los campos `reason`, `hint` y
`screenshot_id` en `stderr` para que los agentes puedan reintentar con un ID anterior o reportar
el motivo exacto del bloqueo. Valida las salidas exitosas con `file PATH` antes de pasarlas
a herramientas de visión.

## Ejemplo práctico: bucle de agente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca el CLI de omi en modo JSON, lanzando una excepción en códigos de salida distintos de cero."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # El CLI imprime errores estructurados en stderr en modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi salió con código {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leer todos los elementos de acción abiertos y marcar como completados aquellos con más de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Manejo de límites de velocidad (rate limits)

Recuerdos: 120/h. Conversaciones: 25/h. Creaciones por lotes: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de velocidad alcanzado
    err = json.loads(result.stderr)
    # err["detail"] tiene el formato: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Usa `--profile <nombre>` si tu agente gestiona varias cuentas de Omi. Cada
  perfil tiene sus propias credenciales y base de API.
* Usa `--api-base http://localhost:8080` para pruebas de backend local.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para anular la configuración de la API Desktop
  local del perfil para una sola ejecución.
* Usa `--verbose` para depuración: registra `METHOD path status (Ns)` en `stderr`
  sin afectar `stdout`, manteniendo el flujo JSON válido.
* Para enviar contenido a una conversación mediante tuberías (pipes), usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
