# omi-cli para agentes

> Guia prático para harnesses controlados por LLM (Claude Code, Cursor, seus próprios bots).

## Por que a CLI é amigável para agentes

* **Contrato JSON estável.** `--json` emite um documento JSON válido para stdout e
  *somente* um documento JSON — sem mensagens de progresso, sem spinners. Erros vão para
  stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estáveis.** `0` ok / `1` uso / `2` auth / `3` servidor / `4` limite
  de taxa / `5` não encontrado. Agentes podem ramificar nisso sem analisar
  erros em linguagem natural.
* **Sem prompts interativos em contextos headless.** Use `--yes` (ou `-y`) para
  comandos destrutivos; use `--api-key` ou defina `OMI_API_KEY` para pular o
  login interativo.
* **Comportamento de retry tolerante.** `429` e `5xx` são repetidos com backoff
  antes de aparecerem.

## Auth (uma vez, pelo humano)

O usuário obtém uma chave de API de desenvolvimento no app web do Omi
(`https://app.omi.me` → Developer → API Keys) e então:

```bash
omi auth login                          # colagem interativa; a chave não fica no histórico do shell
# ou
export OMI_API_KEY=omi_dev_...          # efêmero, amigável para contêineres
```

## As cinco coisas que agentes mais fazem

### 1. Ler memórias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Criar uma memória

```bash
omi memory create --json "O usuário prefere modo escuro" --category lifestyle
```

### 3. Ler conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler itens de ação abertos

```bash
omi action-item list --json --open
```

### 5. Marcar um item de ação como concluído

```bash
omi action-item complete --json a1b2c3d4
```

## API local do Desktop

Quando o Omi Desktop expõe sua API local, agentes podem consultar histórico de
tela, recaps, SQL e tarefas no dispositivo sem usar a API de desenvolvimento na nuvem:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou, para sessões efêmeras:
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

Só conclua ou exclua tarefas quando o usuário pedir claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` grava o screenshot em
disco e ainda imprime JSON em stdout para scripts. O ID do screenshot geralmente
vem de `local search-screen` ou de SQL sobre a tabela `screenshots`. Se o Desktop
retornar uma falha estruturada como `screenshot_pending`, `screenshot_file_missing`,
ou `screenshot_chunk_corrupted`, o modo JSON preserva os campos `reason`, `hint` e
`screenshot_id` em stderr para que agentes possam tentar novamente com um ID mais antigo ou relatar o
bloqueio exato. Valide saídas bem-sucedidas com `file PATH` antes de passá-las
para ferramentas de visão.

## Exemplo completo: loop de agente em Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca a CLI omi em modo JSON, levantando erro em códigos de saída não bem-sucedidos."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # A CLI imprime erros estruturados em stderr no modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi saiu com {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Lê todos os itens de ação abertos e marca como concluído qualquer um com mais de 30 dias.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Lidando com limites de taxa

Memórias: 120/h. Conversas: 25/h. Criações em lote: 15/h.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite de taxa
    err = json.loads(result.stderr)
    # err["detail"] se parece com: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Dicas

* Use `--profile <name>` se seu agente alterna entre várias contas Omi. Cada
  perfil tem sua própria credencial e base de API.
* Use `--api-base http://localhost:8080` para testes com backend local.
* Use `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para sobrescrever as configurações
  locais da API do Desktop do perfil em uma execução.
* Use `--verbose` para depuração — ele registra `METHOD path → status (Ns)` em stderr
  sem afetar stdout, então o modo JSON permanece válido.
* Para canalizar conteúdo para uma conversa, use `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
