# omi-cli pa axentes

> Guía práutica pa harnesses empobinaos por LLM (Claude Code, Cursor, los tos propios bots).

## Poroqué la CLI ye amiga pa axentes

* **Contratu JSON estable.** `--json` emite un documentu JSON válidu a stdout y
  *namái* un documentu JSON — ensin mensaxes de progresu, ensin spinners. Los errores
  van a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de salida estables.** `0` bien / `1` usu / `2` auth / `3` servidor /
  `4` llímite de velocidá / `5` non atopáu. Los axentes puen ramificar nestos
  ensin analizar errores en llingua natural.
* **Ensin prompts interactivos en contestos headless.** Pasa `--yes` (o `-y`) a los
  comandos destructivos; pasa `--api-key` o pon `OMI_API_KEY` pa saltar el
  login interactivu.
* **Comportamientu de reintentu perdonable.** `429` y `5xx` reténtense con
  backoff enantes de salir.

## Auth (una vegada, pola persona)

L'usuariu coya una clave dev API de l'aplicación web Omi
(`https://app.omi.me` → Developer → API Keys) y o:

```bash
omi auth login                          # pegáu interactivu; la clave nun queda na hestoria de la shell
# o
export OMI_API_KEY=omi_dev_...          # efímera, ideal pa contenedores
```

## Les cinco coses que los axentes faen más

### 1. Lleer memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear una memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Lleer conversaciones

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Lleer puntos d'aición abiertos

```bash
omi action-item list --json --open
```

### 5. Marcar un puntu d'aición como fechu

```bash
omi action-item complete --json a1b2c3d4
```

## API llocal de Desktop

Cuandu Omi Desktop espone la so API llocal, los axentes puen entrugar la hestoria
de pantalla del dispositivu, recapitulaciones, SQL y xeres ensin usar l'API dev
de la ñube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# o, pa sesiones efímeres:
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

Acaba o desanicia xeres namái cuandu l'usuariu lo pide claro:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe la captura de pantalla
nel discu y entá imprime JSON a stdout pa scripts. L'ID de captura vien davezu de
`local search-screen` o SQL sobre la tabla `screenshots`. Si Desktop devuelve
un erru estructurau como `screenshot_pending`, `screenshot_file_missing` o
`screenshot_chunk_corrupted`, el mou JSON conserva los campos `reason`, `hint` y
`screenshot_id` a stderr pa que los axentes puedan retentar un ID más antiguu o
informar del bloquéu esautu. Valida les salíes buenes con `file PATH` enantes
de pasales a ferramientes de visión.

## Exemplu trabayáu: bucle d'axente en Python

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

## Xestión de los llímites de velocidá

Memories: 120/h. Conversaciones: 25/h. Creaciones en llote: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Conseyos

* Usa `--profile <name>` si'l to axente xestiona dellos cuentes Omi. Cada perfil
  tien les sos credenciales y base API propies.
* Usa `--api-base http://localhost:8080` pa pruebes de backend llocales.
* Usa `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` pa sustituyir los axustes de l'API
  llocal Desktop del perfil pa una execución.
* Usa `--verbose` pa depurar — rexistra `METHOD path → status (Ns)` a stderr
  ensin afeutar stdout, asina'l mou JSON sigue válidu.
* Pa pipear conteníu nuna conversación, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
