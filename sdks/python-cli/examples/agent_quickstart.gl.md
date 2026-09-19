# omi-cli para axentes de IA

> Guía práctica para contornas impulsadas por LLM (Claude Code, Cursor, os teus propios bots).

## Por que a CLI é amigable para os axentes

* **Contrato JSON estable.** O sinalador `--json` emite un documento JSON válido a stdout e
  *unicamente* un documento JSON — sen mensaxes de progreso nin indicadores de carga. Os
  erros envíanse a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` correcto / `1` erro de uso / `2` autenticación / `3` servidor /
  `4` límite de taxa superado / `5` non atopado. Os axentes poden ramificarse directamente baseándose
  nestes códigos sen necesidade de analizar erros en linguaxe natural.
* **Sen solicitudes interactivas en contextos headless.** Pasa `--yes` (ou `-y`) para ordes
  destrutivas; pasa `--api-key` ou define `OMI_API_KEY` para omitir o inicio de sesión interactivo.
* **Comportamento de reintento comprensivo.** Os erros `429` e `5xx` reinténtanse automaticamente
  cunha espera exponencial (backoff) antes de manifestarse.

## Autenticación (unha soa vez, polo humano)

O usuario obtén unha clave API de desenvolvedor desde a aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) e realiza un dos seguintes pasos:

```bash
omi auth login                          # pegado interactivo; a clave non se garda no historial da shell
# ou
export OMI_API_KEY=omi_dev_...          # efémero, apto para contedores
```

## As cinco accións que os axentes fan con máis frecuencia

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

### 4. Ler tarefas de acción abertas

```bash
omi action-item list --json --open
```

### 5. Marcar unha tarefa de acción como completada

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cando Omi Desktop expón a súa API local, os axentes poden consultar o historial de pantalla
do dispositivo, resumos, datos SQL e tarefas sen usar a API dev na nube:

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

Completa ou elimina tarefas só cando o usuario o solicite explicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

A orde `omi local screenshot SCREENSHOT_ID --output PATH` garda a captura de pantalla no disco
e continúa imprimindo JSON en stdout para os scripts. O ID da captura provén habitualmente de
`local search-screen` ou dunha consulta SQL sobre a táboa `screenshots`. Se Desktop devolve un
erro estruturado como `screenshot_pending`, `screenshot_file_missing` ou `screenshot_chunk_corrupted`,
o modo JSON conserva os campos `reason`, `hint` e `screenshot_id` en stderr para que os axentes poidan
probar un ID máis antigo ou informar do obstáculo exacto. Valida as saídas correctas con `file PATH`
antes de pasalas a ferramentas de visión artificial.

## Exemplo práctico: bucle de axente en Python

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

## Xestión dos límites de taxa (Rate Limits)

Memorias: 120/hora. Conversas: 25/hora. Creacións por lotes: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Usa `--profile <name>` se o teu axente xestiona varias contas de Omi. Cada perfil ten as
  súas propias credenciais e URL base de API.
* Usa `--api-base http://localhost:8080` para probas locais do backend.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para anular a configuración local da API de Desktop
  dun perfil para unha única execución.
* Usa `--verbose` para depuración — rexistra `METHOD path → status (Ns)` en stderr sen afectar
  a stdout, polo que o modo JSON segue sendo válido.
* Para canalizar contido cara a unha conversa, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
