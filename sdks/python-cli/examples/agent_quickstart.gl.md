# omi-cli para axentes (Galician)

> Guía práctica para sistemas baseados en LLM (Claude Code, Cursor, os teus propios bots).

## Por que esta CLI é ideal para axentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido cara a stdout e *unicamente* un documento JSON — sen mensaxes de progreso nin indicadores de carga (spinners). Os erros envíanse a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` correcto / `1` erro de uso / `2` autenticación / `3` erro de servidor / `4` límite de taxa (rate limited) / `5` non atopado. Os axentes poden ramificar a súa lóxica segundo estes códigos sen necesidade de procesar mensaxes en linguaxe natural.
* **Sen solicitudes interactivas en contornos headless.** Engade `--yes` (ou `-y`) para ordes destrutivas; pasa `--api-key` ou define `OMI_API_KEY` para omitir o inicio de sesión interactivo.
* **Comportamento de reintento tolerante.** Os erros `429` e `5xx` reinténtanse automaticamente con retroceso exponencial antes de xerar unha excepción.

## Autenticación (unha única vez, por un humano)

O usuario obtén unha chave de API para desenvolvedores na aplicación web de Omi (`https://app.omi.me` → Developer → API Keys) e configúraa:

```bash
omi auth login                          # pegado interactivo; a chave non queda no historial da shell
# ou
export OMI_API_KEY=omi_dev_...          # efémero, axeitado para contedores (Docker)
```

## As cinco operacións máis habituais dos axentes

### 1. Ler memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear unha memoria

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ler conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler tarefas pendentes (action items)

```bash
omi action-item list --json --open
```

### 5. Marcar unha tarefa como completada

```bash
omi action-item complete --json a1b2c3d4
```

## API local de escritorio (Local Desktop API)

Cando Omi Desktop expón a súa API local, os axentes poden consultar o historial de pantalla, resumos, consultas SQL e tarefas do dispositivo sen usar a API na nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou para sesións efémeras:
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

Só completa ou elimina tarefas cando o usuario o solicite de forma explícita:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

A orde `omi local screenshot SCREENSHOT_ID --output PATH` garda a captura de pantalla no disco e imprime a resposta JSON en stdout para os scripts. O ID da captura provén normalmente de `local search-screen` ou de consultas SQL sobre a táboa `screenshots`. Se Desktop devolve un fallo estruturado (como `screenshot_pending`, `screenshot_file_missing` ou `screenshot_chunk_corrupted`), o modo JSON preserva os campos `reason`, `hint` e `screenshot_id` en stderr para que os axentes poidan reintentar cun ID anterior ou indicar o bloqueo exacto. Valida os ficheiros xerados con `file PATH` antes de envialos a ferramentas de visión.

## Exemplo práctico: Bucle de axente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca a CLI omi en modo JSON, lanzando un erro en códigos de saída distintos de 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # A CLI imprime erros estruturados en stderr no modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi rematou co código {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ler todas as tarefas pendentes e marcar como completadas as de máis de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xestión de límites de taxa (Rate Limits)

Memorias: 120/hora. Conversas: 25/hora. Creacións por lotes: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de taxa acadado
    err = json.loads(result.stderr)
    # err["detail"] ten un formato como: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Emprega `--profile <nome>` se o teu axente xestiona varias contas de Omi. Cada perfil conta coas súas propias credenciais e URL base da API.
* Emprega `--api-base http://localhost:8080` para probas locais do backend.
* Emprega `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para substituír a configuración da API local de escritorio nunha execución concreta.
* Emprega `--verbose` para depuración — rexistra `METHOD ruta → estado (Ns)` en stderr sen afectar a stdout, mantendo a integridade do modo JSON.
* Para canalizar contido cara a unha conversa (piping), emprega `--text -`:
  ```bash
  cat notas_reunion.md | omi conversation create --text - --text-source other_text
  ```
