# omi-cli para agentes

> Guia prático para harnesses orientados por LLM (Claude Code, Cursor, os seus próprios bots).

## Por que a CLI é amigável para agentes

* **Contrato JSON estável.** `--json` emite em stdout um documento JSON válido e
  *apenas* um documento JSON — sem mensagens de progresso, sem spinners. Os erros
  vão para stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estáveis.** `0` ok / `1` uso incorreto / `2` autenticação /
  `3` servidor / `4` limite de taxa / `5` não encontrado. Os agentes podem
  ramificar com base nesses valores sem interpretar erros em linguagem natural.
* **Sem prompts interativos em contextos headless.** Passe `--yes` (ou `-y`) aos
  comandos destrutivos; passe `--api-key` ou defina `OMI_API_KEY` para pular o
  login interativo.
* **Comportamento tolerante de retentativa.** `429` e `5xx` são repetidos com
  backoff antes de serem reportados.

## Autenticação (uma única vez, feita pela pessoa)

A pessoa obtém uma chave de desenvolvedor no aplicativo web do Omi
(`https://app.omi.me` → Developer → API Keys) e faz uma destas duas coisas:

```bash
omi auth login                          # colagem interativa; a chave não fica no histórico do shell
# ou
export OMI_API_KEY=omi_dev_...          # efêmera, boa para contêineres
```

## As cinco coisas que os agentes mais fazem

### 1. Ler memórias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Criar uma memória

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ler conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler itens de ação em aberto

```bash
omi action-item list --json --open
```

### 5. Marcar um item de ação como concluído

```bash
omi action-item complete --json a1b2c3d4
```

## API local do Desktop

Quando o Omi Desktop expõe sua API local, os agentes podem consultar o histórico
de tela, os resumos, SQL e as tarefas do dispositivo sem usar a API de
desenvolvedor na nuvem:

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

Conclua ou exclua tarefas apenas quando a pessoa pedir claramente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` grava a captura de tela em
disco e continua imprimindo JSON em stdout para scripts. O ID da captura
normalmente vem de `local search-screen` ou de um SQL sobre a tabela
`screenshots`. Se o Desktop retornar uma falha estruturada como
`screenshot_pending`, `screenshot_file_missing` ou `screenshot_chunk_corrupted`,
o modo JSON preserva os campos `reason`, `hint` e `screenshot_id` em stderr, para
que o agente possa tentar novamente com um ID mais antigo ou relatar o bloqueio
exato. Valide as saídas bem-sucedidas com `file PATH` antes de passá-las a
ferramentas de visão.

## Exemplo completo: loop de agente em Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoca a CLI omi em modo JSON e lança uma exceção em códigos de saída diferentes de 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Em modo JSON a CLI imprime erros estruturados em stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ler todos os itens de ação em aberto e concluir os que tiverem mais de 30 dias.
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
    # err["detail"] tem esta forma: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Dicas

* Use `--profile <name>` se o seu agente lida com várias contas do Omi. Cada
  perfil tem sua própria credencial e seu próprio API base.
* Use `--api-base http://localhost:8080` para testar contra um backend local.
* Use `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para sobrescrever, em uma única
  execução, as configurações da API do Desktop salvas no perfil.
* Use `--verbose` para depurar — ele registra `METHOD path → status (Ns)` em
  stderr sem afetar stdout, então o modo JSON continua válido.
* Para enviar conteúdo a uma conversa por pipe, use `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
