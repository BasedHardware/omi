# omi-cli para axentes

> Guía práctica para ferramentas dirixidas por LLM (Claude Code, Cursor, os teus propios bots).

## Por que o CLI é axeitado para axentes

* **Contrato JSON estable.** `--json` envía un documento JSON válido a stdout e
  *unicamente* un documento JSON — sen mensaxes de progreso nin animacións. Os erros van a
  stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` correcto / `1` erro de uso / `2` autenticación / `3` erro do servidor / `4` límite de solicitudes / `5` non atopado. Os axentes poden ramificar en función destes sen necesidade de interpretar erros en linguaxe natural.
* **Sen solicitudes interactivas en contextos sen cabeza.** Pasa `--yes` (ou `-y`) para
  ordes destrutivas; pasa `--api-key` ou define `OMI_API_KEY` para omitir o inicio de sesión interactivo.
* **Comportamento tolerante de reintento.** As respostas `429` e `5xx` reinténtanse con tempo de espera
  antes de manifestarse.

## Autenticación (unha soa vez, polo humano)

O usuario obtén unha clave de API de desenvolvedor na aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) e realiza unha das seguintes opcións:

```bash
omi auth login                          # pegado interactivo; a clave non queda no historial do terminal
# ou
export OMI_API_KEY=omi_dev_...          # efémero, axeitado para contedores
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

### 4. Ler tarefas pendentes abertas

```bash
omi action-item list --json --open
```

### 5. Marcar unha tarefa pendente como rematada

```bash
omi action-item complete --json a1b2c3d4
```

## API de escritorio local (Desktop API)

Cando Omi Desktop expón a súa API local, os axentes poden consultar o historial de pantalla do dispositivo,
resumos, SQL e tarefas sen utilizar a API na nube:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou, para sesións efémeras:
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

Só completa ou elimina tarefas cando o usuario o solicite de maneira expresa:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

A orde `omi local screenshot SCREENSHOT_ID --output PATH` garda a captura de pantalla no
disco e segue a imprimir JSON en stdout para scripts. O identificador da captura adoita provir
de `local search-screen` ou de consultas SQL sobre a táboa `screenshots`. Se Desktop
devolve un erro estruturado como `screenshot_pending`, `screenshot_file_missing`,
ou `screenshot_chunk_corrupted`, o modo JSON preserva os campos `reason`, `hint` e
`screenshot_id` en stderr para que os axentes poidan reintentar cun identificador anterior ou
informar do obstáculo exacto. Valida as saídas correctas con `file PATH` antes de pasalas
a ferramentas de visión.

## Exemplo práctico: bucle de axente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca omi CLI en modo JSON, lanzando unha excepción en caso de erro."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # O CLI imprime erros estruturados en stderr en modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Le todas as tarefas abertas e marca como completadas as que teñan máis de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xestión de límites de velocidade (rate limits)

Memorias: 120/h. Conversas: 25/h. Creacións por lotes: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de solicitudes acadado
    err = json.loads(result.stderr)
    # err["detail"] ten un formato como: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Emprega `--profile <nome>` se o teu axente xestiona varias contas de Omi. Cada
  perfil dispón das súas propias credenciais e base de API.
* Emprega `--api-base http://localhost:8080` para probas con servidores locais.
* Emprega `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para anular a configuración local
  da Desktop API do perfil nunha única execución.
* Emprega `--verbose` para depuración — rexistra `METHOD path → status (Ns)` en stderr
  sen afectar a stdout, mantendo válido o modo JSON.
* Para enviar contido a unha conversa mediante canalización, emprega `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
