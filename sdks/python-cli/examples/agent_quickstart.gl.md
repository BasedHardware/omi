# omi-cli para axentes

> Guía práctica para arneses impulsados por LLM (Claude Code, Cursor, os teus propios bots).

## Por que a CLI é amigable para axentes

* **Contrato JSON estable.** `--json` emite un documento JSON válido a stdout e
  *só* un documento JSON — sen mensaxes de progreso, sen indicadores de espera.
  Os erros van a stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estables.** `0` ok / `1` uso / `2` autenticación / `3` servidor / `4` límite
  de peticións / `5` non atopado. Os axentes poden ramificar con estes sen analizar
  erros en linguaxe natural.
* **Sen solicitudes interactivas en contextos headless.** Pasa `--yes` (ou `-y`) a
  comandos destrutivos; pasa `--api-key` ou define `OMI_API_KEY` para evitar o
  inicio de sesión interactivo.
* **Comportamento de reintento tolerante.** `429` e `5xx` reintentanse con retroceso
  antes de amosarse.

## Autenticación (unha soa vez, polo humano)

O usuario obtén unha clave de API de desenvolvedor desde a aplicación web de Omi
(`https://app.omi.me` → Developer → API Keys) e logo:

```bash
omi auth login                          # pegado interactivo; a clave non queda no historial do shell
# ou
export OMI_API_KEY=omi_dev_...          # efémera, apta para contedores
```

## As cinco cousas que os axentes fan máis

### 1. Ler memorias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Crear unha memoria

```bash
omi memory create --json "O usuario prefire o modo escuro" --category lifestyle
```

### 3. Ler conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler elementos de acción abertos

```bash
omi action-item list --json --open
```

### 5. Marcar un elemento de acción como feito

```bash
omi action-item complete --json a1b2c3d4
```

## API local de Desktop

Cando Omi Desktop expón a súa API local, os axentes poden consultar o historial
de pantalla no dispositivo, resumos, SQL e tarefas sen usar a API de desenvolvedor na nube:

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

Só completa ou elimina tarefas cando o usuario o pida claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` escribe a captura de pantalla en
disco e aínda imprime JSON a stdout para os scripts. O ID da captura normalmente
provén de `local search-screen` ou de SQL sobre a táboa `screenshots`. Se Desktop
devolve un fallo estruturado como `screenshot_pending`, `screenshot_file_missing`,
ou `screenshot_chunk_corrupted`, o modo JSON conserva os campos `reason`, `hint` e
`screenshot_id` en stderr para que os axentes poidan reintentar un ID máis antigo ou informar
do bloqueo exacto. Valida as saídas correctas con `file PATH` antes de pasalas
ás ferramentas de visión.

## Exemplo práctico: bucle de axente en Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca a CLI omi en modo JSON, lanzando unha excepción con códigos de saída distintos de cero."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # A CLI imprime erros estruturados a stderr en modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi saíu con {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Le todos os elementos de acción abertos e marca como completos os que teñan máis de 30 días.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xestión de límites de peticións

Memorias: 120/h. Conversas: 25/h. Creacións por lotes: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # límite de peticións alcanzado
    err = json.loads(result.stderr)
    # err["detail"] parécese a: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Consellos

* Usa `--profile <name>` se o teu axente xestiona varias contas de Omi. Cada
  perfil ten as súas propias credenciais e base de API.
* Usa `--api-base http://localhost:8080` para probas locais do backend.
* Usa `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para sobrescribir a configuración
  local da API de Desktop dun perfil durante unha execución.
* Usa `--verbose` para depurar — rexistra `METHOD path → status (Ns)` en stderr
  sen afectar a stdout, polo que o modo JSON segue sendo válido.
* Para canalizar contido nunha conversa, usa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
