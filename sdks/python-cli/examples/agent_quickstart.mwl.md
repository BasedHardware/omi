# omi-cli pa ls agentes

> Guia prático pa sistemas dirigidos por LLM (Claude Code, Cursor, ls sous própios bots).

## Porque l CLI ye amigo de ls agentes

* **Cuntrato JSON stable.** `--json` mite un bálido documento JSON pa stdout i
  *apenas* un documento JSON — sin mensaiges de progreso, sin spinners. Erros ban
  pa stderr cumo `{"error": "...", "detail": "..."}`.
* **Códigos de salida stabales.** `0` ok / `1` uso / `2` outenticaçon /
  `3` serbidor / `4` lhemite de requisiçones / `5` nun ancontrado. Agentes puoden
  ramificar cun eilhes sin analisar erros an lhéngua natural.
* **Nun hai prompts eiteratibos an cuntestos headless.** Passa `--yes` (ó `-y`) pa
  cumandos destructibos; passa `--api-key` ó define `OMI_API_KEY` pa saltar l
  lhogin eiteratibo.
* **Cumportamiento de repetiçones tolerante.** `429` i `5xx` son repetidos cun backoff
  antes de ser apersentados.

## Outenticaçon (ua beç, pul houmano)

L'usuario oubten ua chabe API de zambolbimiento de la aplicaçon web Omi
(`https://app.omi.me` → Developer → API Keys) i depuis:

```bash
omi auth login                          # quelar eiteratibo; chabe nun stá ne l stórico de la shell
# ó
export OMI_API_KEY=omi_dev_...          # eifémera, adequada la cunteneres
```

## Las cinco cousas que ls agentes fázen mais a miús

### 1. Ler mimórias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Qujar ua mimória

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ler cumbersas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler eitens d'açon abertos

```bash
omi action-item list --json --open
```

### 5. Marcar un eitem d'açon cumo cuncluído

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API

Quando l Omi Desktop spon l sou API local, ls agentes puoden cunsultar l stórico de l
ecrán ne l çpositibo, resumos, SQL i tarefas sin ousar l cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ó, pa sesones eifémeras:
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

Solo cunclui ó apaga tarefas quando l'usuario pede claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` scribe la captura de l ecrán ne l
çco i cuntina a eimprimir JSON pa stdout pa scripts. L ID de la captura normalmente
ben de `local search-screen` ó de SQL subre la tabela `screenshots`. Se l Desktop
debolbe ua falha struturada cumo `screenshot_pending`, `screenshot_file_missing` ó
`screenshot_chunk_corrupted`, l modo JSON perserba ls campos `reason`, `hint` i
`screenshot_id` ne l stderr, para que ls agentes puodan tentar un ID mais bielho ó
relatar l bloqueio eisato. Balide resultados ben sucedidos cun `file PATH` antes de
ls passar la ferramientas de beison.

## Eisemplo trabalhado: ciclo de agente an Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Chamar l CLI omi an modo JSON, lhantando ua sceiçon an códigos de salida nun sucedidos."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # L CLI eimprime erros struturados ne l stderr an modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ler todos ls eitens d'açon abertos i marcar ls mais bielhos que 30 dies cumo cuncluídos.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Lidar cun lhemites de requisiçones

Mimórias: 120/h. Cumbersas: 25/h. Criaçones an lote: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # lhemite de requisiçones
    err = json.loads(result.stderr)
    # err["detail"] parece algo cumo: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Cundilhas

* Ousa `--profile <name>` se l sou agente gerencia bários cuontas Omi. Cada perfil
  ten sues própias credenciales i base API.
* Ousa `--api-base http://localhost:8080` pa testar l backend local.
* Ousa `OMI_LOCAL_API_URL` i `OMI_LOCAL_TOKEN` pa subrepor las figuras de l Desktop
  API de l perfil durante ua sola eisecuçon.
* Ousa `--verbose` pa depurar — registra `METHOD path → status (Ns)` ne l stderr
  sin afetar l stdout, de maneira que l modo JSON quede bálido.
* Pa ancanhar cuntenido nua cumbersa, ousa `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```