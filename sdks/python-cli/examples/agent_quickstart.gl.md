# omi-cli para axentes

> Guía práctica para harnesses guiados por LLM (Claude Code, Cursor, os teus propios bots).

## Por que a CLI é axeitada para axentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a stdout e
  *só* un documento JSON — sen mensaxes de progreso, sen spinners. Os erros van
  a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` ben / `1` uso / `2` auth / `3` servidor /
  `4` límite de tasa / `5` non atopado. Os axentes poden ramificar neles sen
  analizar erros en linguaxe natural.
* **Sen prompts interactivos en contextos headless.** Pasa `--yes` (ou `-y`) a
  comandos destrutivos; pasa `--api-key` ou establece `OMI_API_KEY` para saltar
  o login interactivo.
* **Comportamento de reintento permisivo.** `429` e `5xx` reinténtanse con
  backoff antes de saír á superficie.

## Auth (unha vez, polo humano)

O usuario obtén unha clave dev API da aplicación web Omi
(`https://app.omi.me` → Developer → API Keys) e ben:

```bash
omi auth login                          # pegado interactivo; a clave non queda no historial do shell
# ou
export OMI_API_KEY=omi_dev_...          # efímera, axeitada para contedores
```

## As cinco cousas que os axentes fan máis

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

### 4. Ler puntos de acción abertos

```bash
omi action-item list --json --open
```

### 5. Marcar un punto de acción como feito

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cando Omi Desktop expón a súa API local, os axentes poden consultar o historial
de pantalla do dispositivo, resumos, SQL e tarefas sen usar a API dev da nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou, para sesións efímeras:
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

Completa ou elimina tarefas só cando o usuario o pida claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe a captura de pantalla
no disco e aínda imprime JSON a stdout para scripts. O ID da captura adoita vir
de `local search-screen` ou SQL sobre a táboa `screenshots`. Se Desktop devolve
un erro estruturado como `screenshot_pending`, `screenshot_file_missing` ou
`screenshot_chunk_corrupted`, o modo JSON preserva os campos `reason`, `hint` e
`screenshot_id` en stderr para que os axentes poidan reintentar un ID máis vello
ou informar do bloqueo exacto. Valida as saídas correctas con `file PATH` antes
de pasarlas ás ferramentas de visión.

## Exemplo traballado: bucle de axente en Python

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

## Xestión dos límites de tasa

Lembranzas: 120/h. Conversas: 25/h. Creacións en lote: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Usa `--profile <name>` se o teu axente xestiona varias contas Omi. Cada perfil
  ten as súas propias credenciais e base de API.
* Usa `--api-base http://localhost:8080` para probas de backend locais.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para anular os axustes da API de
  Desktop locais do perfil nunha única execución.
* Usa `--verbose` para depurar — rexistra `METHOD path → status (Ns)` en stderr
  sen afectar stdout, polo que o modo JSON segue sendo válido.
* Para facer pipe de contido nunha conversa, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
