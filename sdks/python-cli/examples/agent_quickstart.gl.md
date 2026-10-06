# omi-cli para axentes

> Guía práctica para contornas controladas por LLM (Claude Code, Cursor ou os teus propios bots).

## Por que o CLI é axeitado para axentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido en stdout e
  *soamente* un documento JSON: non amosa mensaxes de progreso nin spinners. Os
  erros van a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` correcto / `1` uso incorrecto / `2`
  autenticación / `3` servidor / `4` límite de solicitudes / `5` non atopado.
  Os axentes poden tomar decisións con eles sen analizar erros en linguaxe natural.
* **Sen avisos interactivos en contextos headless.** Pasa `--yes` (ou `-y`) aos
  comandos destrutivos; pasa `--api-key` ou define `OMI_API_KEY` para omitir
  o inicio de sesión interactivo.
* **Reintentos tolerantes.** Os códigos `429` e `5xx` reinténtanse con backoff
  antes de devolverse á persoa usuaria.

## Autenticación (unha soa vez, pola persoa usuaria)

A persoa usuaria obtén unha clave API de desenvolvemento desde a aplicación web
de Omi (`https://app.omi.me` → Developer → API Keys) e usa unha destas opcións:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## As cinco tarefas que máis fan os axentes

### 1. Ler lembranzas

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear unha lembranza

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ler conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler tarefas pendentes

```bash
omi action-item list --json --open
```

### 5. Marcar unha tarefa como rematada

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cando Omi Desktop expón a súa API local, os axentes poden consultar o historial
de pantalla do dispositivo, resumos, SQL e tarefas sen usar a API de desenvolvemento
na nube:

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

Completa ou elimina tarefas só cando a persoa usuaria o solicite con claridade:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe a captura no disco e
tamén imprime JSON en stdout para os scripts. O ID de captura adoita provir de
`local search-screen` ou de SQL sobre a táboa `screenshots`. Se Desktop devolve
un fallo estruturado como `screenshot_pending`, `screenshot_file_missing` ou
`screenshot_chunk_corrupted`, o modo JSON conserva os campos `reason`, `hint` e
`screenshot_id` en stderr para que o axente poida reintentar cun ID anterior ou
informar do bloqueo exacto. Valida as saídas correctas con `file PATH` antes de
pasalas a ferramentas de visión.

## Exemplo completo: ciclo dun axente Python

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

## Como xestionar os límites de solicitudes

Lembranzas: 120 por hora. Conversas: 25 por hora. Creacións por lotes: 15 por hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Usa `--profile <name>` se o teu axente alterna entre varias contas de Omi. Cada
  perfil ten as súas propias credenciais e base de API.
* Usa `--api-base http://localhost:8080` para probar o backend local.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para substituír a configuración
  da API de Desktop do perfil nunha soa execución.
* Usa `--verbose` para depurar: rexistra `METHOD path → status (Ns)` en stderr
  sen modificar stdout, polo que o modo JSON segue sendo válido.
* Para pasar contido a unha conversa, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
