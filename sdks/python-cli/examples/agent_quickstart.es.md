# omi-cli para agentes

> Guía práctica para entornos impulsados por LLM (Claude Code, Cursor, tus propios bots).

## Por qué la CLI es ideal para agentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a stdout y
  *únicamente* un documento JSON — sin mensajes de progreso, sin indicadores de carga. Los errores se envían a
  stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` correcto / `1` uso incorrecto / `2` fallo de autenticación / `3` error de servidor / `4` límite
  de velocidad alcanzado (rate limited) / `5` no encontrado. Los agentes pueden ramificar su lógica sobre estos códigos sin analizar
  mensajes de error en lenguaje natural.
* **Sin confirmaciones interactivas en contextos desatendidos (headless).** Pasa `--yes` (o `-y`) para
  comandos destructivos; pasa `--api-key` o define `OMI_API_KEY` para omitir el
  inicio de sesión interactivo.
* **Comportamiento de reintento tolerante.** Los errores `429` y `5xx` se reintentan con retroceso exponencial (backoff)
  antes de emerger.

## Autenticación (una sola vez, por el humano)

El usuario obtiene una clave de API de desarrollador desde la aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) y realiza una de las siguientes opciones:

```bash
omi auth login                          # pegado interactivo; la clave no queda en el historial de la terminal
# o bien
export OMI_API_KEY=omi_dev_...          # efímero, ideal para contenedores
```

## Las cinco cosas que los agentes hacen con más frecuencia

### 1. Leer recuerdos

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

Cuando Omi Desktop expone su API local, los agentes pueden consultar el historial de
pantalla en el dispositivo, resúmenes, SQL y tareas sin utilizar la API de desarrollo en la nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o bien, para sesiones efímeras:
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

Completa o elimina tareas únicamente cuando el usuario lo solicite de forma explícita:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` guarda la captura de pantalla en el
disco y mantiene la salida JSON en stdout para scripts. El ID de la captura suele
provenir de `local search-screen` o de una consulta SQL sobre la tabla `screenshots`. Si Desktop
devuelve un error estructurado como `screenshot_pending`, `screenshot_file_missing`,
o `screenshot_chunk_corrupted`, el modo JSON preserva los campos `reason`, `hint` y
`screenshot_id` en stderr para que los agentes puedan reintentar con un ID anterior o reportar el
bloqueo exacto. Valida que los archivos sean correctos con `file PATH` antes de pasarlos
a herramientas de visión.

## Ejemplo práctico: bucle de agente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca la CLI de omi en modo JSON, lanzando excepción en códigos de salida distintos de cero."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # La CLI imprime errores estructurados en stderr en modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi finalizó con código {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lee todos los elementos de acción pendientes y marca como completados los de más de 30 días de antigüedad.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Gestión de límites de velocidad (rate limits)

Recuerdos: 120/h. Conversaciones: 25/h. Creación en lote: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de velocidad alcanzado
    err = json.loads(result.stderr)
    # err["detail"] tiene el formato: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Utiliza `--profile <nombre>` si tu agente gestiona múltiples cuentas de Omi. Cada
  perfil dispone de sus propias credenciales y base de API.
* Utiliza `--api-base http://localhost:8080` para pruebas contra un backend local.
* Utiliza `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para anular la configuración de la
  API de Desktop para una única ejecución.
* Utiliza `--verbose` para depuración — registra `METHOD path → status (Ns)` en stderr
  sin interferir con stdout, por lo que el modo JSON permanece válido.
* Para enviar contenido directamente a una conversación mediante canalización (pipe), usa `--text -`:
  ```bash
  cat notas_reunion.md | omi conversation create --text - --text-source other_text
  ```
