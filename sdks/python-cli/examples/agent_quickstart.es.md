# omi-cli para agentes

> Guía práctica para harnesses impulsados por LLM (Claude Code, Cursor, tus propios bots).

## Por qué el CLI es amigable para agentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a stdout y
*solamente* un documento JSON — sin mensajes de progreso, sin spinners. Los errores van a
stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` ok / `1` uso / `2` auth / `3` servidor / `4` límite
de peticiones / `5` no encontrado. Los agentes pueden bifurcar según estos códigos sin
parsear errores en lenguaje natural.
* **Sin prompts interactivos en contextos headless.** Pasa `--yes` (o `-y`) a los
comandos destructivos; pasa `--api-key` o define `OMI_API_KEY` para saltarte el
login interactivo.
* **Reintentos tolerantes.** `429` y `5xx` se reintentan con backoff
antes de reportarse.

## Auth (una vez, por el humano)

El usuario obtiene una dev API key desde la web app de Omi
(`https://app.omi.me` → Developer → API Keys) y luego:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Las cinco cosas que los agentes hacen más

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

### 4. Leer action items abiertos

```bash
omi action-item list --json --open
```

### 5. Marcar un action item como completado

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Cuando Omi Desktop expone su API local, los agentes pueden consultar el historial de
pantalla en el dispositivo, recaps, SQL y tareas sin usar la dev API en la nube:

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

Solo completes o elimines tareas cuando el usuario lo pida claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura de pantalla en
disco y aun así imprime JSON a stdout para los scripts. El screenshot ID normalmente
viene de `local search-screen` o de SQL sobre la tabla `screenshots`. Si Desktop
devuelve un fallo estructurado como `screenshot_pending`, `screenshot_file_missing`,
o `screenshot_chunk_corrupted`, el modo JSON preserva los campos `reason`, `hint` y
`screenshot_id` en stderr para que los agentes puedan reintentar con un ID más antiguo
o reportar el bloqueo exacto. Valida las salidas exitosas con `file PATH` antes de
pasarlas a herramientas de visión.

## Ejemplo práctico: bucle de agente en Python

> Nota: el ejemplo siguiente completa action items automáticamente. Ejecútalo
> únicamente con la autorización explícita del usuario.

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

## Manejo de límites de peticiones

Memorias: 120/hora. Conversaciones: 25/hora. Creaciones en lote: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consejos

* Usa `--profile <name>` si tu agente maneja varias cuentas de Omi. Cada
perfil tiene su propia credencial y API base.
* Usa `--api-base http://localhost:8080` para pruebas locales del backend.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` para sobrescribir por una sola ejecución
los ajustes locales del Desktop API del perfil.
* Usa `--verbose` para depurar — registra `METHOD path → status (Ns)` en stderr
sin afectar stdout, así el modo JSON sigue siendo válido.
* Para enviar contenido por pipe a una conversación, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
