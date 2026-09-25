# omi-cli para agentes

> Guía práctica para entornos pilotados por LLM (Claude Code, Cursor, tus propios bots).

## Por qué el CLI es óptimo para agentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido en stdout y
  *únicamente* un documento JSON — sin mensajes de progreso ni indicadores de carga. Los errores se envían a
  stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` éxito / `1` uso incorrecto / `2` error de autenticación / `3` error de servidor / `4` límite
  de tasa alcanzado (rate limited) / `5` no encontrado. Los agentes pueden condicionar su lógica con estos
  códigos sin necesidad de analizar mensajes en lenguaje natural.
* **Sin solicitudes interactivas en contextos sin interfaz (headless).** Pasa `--yes` (o `-y`) a los
  comandos destructivos; pasa `--api-key` o define `OMI_API_KEY` para omitir el
  inicio de sesión interactivo.
* **Comportamiento tolerante con reintentos.** Los errores `429` y `5xx` se reintentan automáticamente
  con retroceso exponencial (backoff) antes de manifestarse.

## Autenticación (única vez, realizada por el humano)

El usuario obtiene una clave de API de desarrollador desde la aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) y realiza alguna de las dos opciones:

```bash
omi auth login                          # pegado interactivo; la clave no queda en el historial del shell
# o
export OMI_API_KEY=omi_dev_...          # efímero, apto para contenedores
```

## Las cinco operaciones más comunes de los agentes

### 1. Leer recuerdos (memories)

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

### 4. Leer tareas pendientes (action items)

```bash
omi action-item list --json --open
```

### 5. Marcar una tarea como completada

```bash
omi action-item complete --json a1b2c3d4
```

## API de Escritorio Local (Local Desktop API)

Cuando Omi Desktop expone su API local, los agentes pueden consultar el historial
de pantalla en el dispositivo, resúmenes, SQL y tareas sin usar la API de desarrollo en la nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, para sesiones efímeras:
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

Solo completa o elimina tareas cuando el usuario lo solicite explícitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura de pantalla en
el disco y continúa imprimiendo JSON en stdout para scripts. El ID de la captura proviene usualmente
de `local search-screen` o de una consulta SQL sobre la tabla `screenshots`. Si Desktop
devuelve un error estructurado como `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, el modo JSON preserva los campos `reason`, `hint` y
`screenshot_id` en stderr para que los agentes puedan reintentar con un ID anterior o reportar el
bloqueo exacto. Valida las salidas exitosas con `file PATH` antes de pasarlas a herramientas de visión.

## Ejemplo práctico: bucle de agente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca el CLI de omi en modo JSON, lanzando excepción si el código de salida no es exitoso."""
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
        raise RuntimeError(f"omi finalizó con código {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lee todas las tareas abiertas y marca como completadas aquellas con más de 30 días de antigüedad.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Manejo de límites de tasa (rate limits)

Recuerdos: 120/h. Conversaciones: 25/h. Creaciones en lote: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de tasa alcanzado
    err = json.loads(result.stderr)
    # err["detail"] tiene el formato: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos y recomendaciones

* Usa `--profile <nombre>` si tu agente administra múltiples cuentas de Omi. Cada
  perfil cuenta con sus propias credenciales y base de API.
* Usa `--api-base http://localhost:8080` para pruebas en entornos locales de backend.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para anular temporalmente la configuración local de
  Desktop API en una ejecución puntual.
* Usa `--verbose` para depuración — registra `METHOD path → status (Ns)` en stderr
  sin afectar a stdout, preservando la validez del modo JSON.
* Para enviar contenido a una conversación mediante una tubería (pipe), usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
