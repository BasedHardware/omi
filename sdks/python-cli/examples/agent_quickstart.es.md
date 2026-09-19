# omi-cli para agentes

> Guía práctica para harnesses dirigidos por LLM (Claude Code, Cursor, tus propios bots).

## Por qué la CLI es apta para agentes

* **Contrato JSON estable.** `--json` emite en stdout un documento JSON válido y
  *solo* un documento JSON: sin mensajes de progreso ni spinners. Los errores van
  a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` ok / `1` uso incorrecto / `2` autenticación /
  `3` servidor / `4` límite de tasa / `5` no encontrado. Los agentes pueden
  ramificar según estos valores sin analizar errores en lenguaje natural.
* **Sin preguntas interactivas en contextos headless.** Pasa `--yes` (o `-y`) a los
  comandos destructivos; pasa `--api-key` o define `OMI_API_KEY` para omitir el
  inicio de sesión interactivo.
* **Reintentos tolerantes.** `429` y `5xx` se reintentan con backoff antes de
  reportarse.

## Autenticación (una sola vez, la hace la persona)

La persona obtiene una clave de desarrollador en la aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) y hace una de estas dos cosas:

```bash
omi auth login                          # pegado interactivo; la clave no queda en el historial del shell
# o
export OMI_API_KEY=omi_dev_...          # efímera, apta para contenedores
```

## Las cinco cosas que más hacen los agentes

### 1. Leer memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear una memoria

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

### 5. Marcar una tarea como completada

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cuando Omi Desktop expone su API local, los agentes pueden consultar el historial
de pantalla, los resúmenes, SQL y las tareas del dispositivo sin usar la API de
desarrollador en la nube:

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

Completa o elimina tareas solo cuando la persona lo pida claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura en disco y
sigue imprimiendo JSON en stdout para los scripts. El ID de la captura suele venir
de `local search-screen` o de una consulta SQL sobre la tabla `screenshots`. Si
Desktop devuelve un fallo estructurado como `screenshot_pending`,
`screenshot_file_missing` o `screenshot_chunk_corrupted`, el modo JSON conserva
los campos `reason`, `hint` y `screenshot_id` en stderr, de modo que el agente
puede reintentar con un ID más antiguo o informar del bloqueo exacto. Valida las
salidas correctas con `file PATH` antes de pasarlas a herramientas de visión.

## Ejemplo completo: bucle de agente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI omi en modo JSON y lanza una excepción si el código de salida no es 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # En modo JSON la CLI imprime errores estructurados en stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Leer todas las tareas abiertas y completar las que tengan más de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestión de los límites de tasa

Memorias: 120/h. Conversaciones: 25/h. Creaciones por lotes: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de tasa
    err = json.loads(result.stderr)
    # err["detail"] tiene esta forma: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Usa `--profile <name>` si tu agente maneja varias cuentas de Omi. Cada
  perfil tiene su propia credencial y su propio API base.
* Usa `--api-base http://localhost:8080` para probar contra un backend local.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para sobrescribir, en una sola
  ejecución, la configuración de la API de Desktop guardada en el perfil.
* Usa `--verbose` para depurar: registra `METHOD path → status (Ns)` en stderr
  sin afectar a stdout, así el modo JSON sigue siendo válido.
* Para enviar contenido a una conversación por tubería, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
