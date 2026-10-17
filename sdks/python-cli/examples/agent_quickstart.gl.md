# omi-cli para axentes

> Guía práctica para harnesses guiados por LLM (Claude Code, Cursor, os teus bots).

## Por que a CLI é amigable para axentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a stdout e *só* JSON — sen mensaxes de progreso nin spinners. Os erros van a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` ok / `1` uso / `2` auth / `3` servidor / `4` rate limited / `5` non atopado. Os axentes poden ramificar nestes sen analizar erros en linguaxe natural.
* **Sen prompts interactivos en contextos headless.** Pasa `--yes` (ou `-y`) aos comandos destrutivos; pasa `--api-key` ou define `OMI_API_KEY` para saltar o login interactivo.
* **Reintento condescendente.** `429` e `5xx` reinténtanse con backoff antes de emerxer.

## Autenticación (unha vez, polo humano)

O usuario obtén unha dev API key da app web de Omi
(`https://app.omi.me` → Developer → API Keys) e:

```bash
omi auth login                          # pegar interactivo; a chave non queda no historial do shell
# # ou
export OMI_API_KEY=omi_dev_...          # efémera, apta para contenedores
```

## As cinco cousas que os axentes máis fan

### 1. Ler memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear unha memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ler conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler os action items abertos

```bash
omi action-item list --json --open
```

### 5. Marcar un action item como feito

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cando Omi Desktop expón a súa API local, os axentes poden consultar
o historial de pantalla no dispositivo, recaps, SQL e tarefas sen a dev API da nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # ou, para sesións efémeras:
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

`omi local screenshot SCREENSHOT_ID --output PATH` escribe a captura de
pantalla ao disco e aínda imprime JSON a stdout para os scripts. O ID da captura
vén normalmente de `local search-screen` ou SQL sobre a táboa `screenshots`. Se
Desktop devolve un fallo estruturado como `screenshot_pending`,
`screenshot_file_missing` ou `screenshot_chunk_corrupted`, o modo JSON conserva
`reason`, `hint` e `screenshot_id` en stderr para que o axente poida reintentar
un ID máis vello ou informar do bloqueo exacto. Valida as saídas correctas con
`file PATH` antes de pasalas a ferramentas de visión.

## Exemplo resolto: bucle de axente Python

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

# Le todos os action items abertos e marca como feitos os maiores de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xestión de rate limits

Memories: 120/hora. Conversations: 25/hora. Creacións en lote: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] ten esta forma: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Usa `--profile <name>` se o axente manexa varias contas Omi. Cada perfil
  ten as súas credenciais e API base propias.
* Usa `--api-base http://localhost:8080` para probas de backend local.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para sobrescribir os axustes
  da API Desktop do perfil nunha soa execución.
* Usa `--verbose` para depuración — rexistra `METHOD path → status (Ns)` en
  stderr sen afectar stdout, polo que o modo JSON segue válido.
* Para enviar contido a unha conversation, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
