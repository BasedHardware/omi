# omi-cli para agentes

> Guia prático para ambientes movidos por LLM (Claude Code, Cursor, seus próprios bots).

## Por que o CLI é amigável para agentes

* **Contrato JSON estável.** `--json` emite um documento JSON válido para stdout e *somente* esse documento — sem mensagens de progresso ou spinners. Erros são escritos em stderr como `{"error": "...", "detail": "..."}`.
* **Códigos de saída estáveis.** `0` ok / `1` erro de uso / `2` erro de autenticação / `3` erro de servidor / `4` limite de taxa atingido / `5` não encontrado. Agentes podem ramificar nesses códigos sem analisar linguagem natural em mensagens de erro.
* **Sem prompts interativos em contextos headless.** Passe `--yes` (ou `-y`) para comandos destrutivos; passe `--api-key` ou defina `OMI_API_KEY` para pular o login interativo.
* **Lógica de repetição tolerante.** `429` e `5xx` são repetidos com backoff exponencial antes de serem relatados.

## Autenticação (uma vez, pelo humano)

O usuário obtém uma chave de API de desenvolvedor no aplicativo web Omi (`https://app.omi.me` → Developer → API Keys) e executa:

```bash
omi auth login                          # pasta interativa; a chave não fica no histórico do shell
# ou
export OMI_API_KEY=omi_dev_...          # temporário, compatível com contêineres
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

### 4. Ler itens de ação abertos

```bash
omi action-item list --json --open
```

### 5. Marcar um item de ação como concluído

```bash
omi action-item complete --json a1b2c3d4
```

## API Local do Desktop

Quando o Omi Desktop expõe sua API local, os agentes podem consultar o histórico de tela do dispositivo, resumos, SQL e tarefas sem usar a API de desenvolvimento na nuvem:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# temporário, compatível com contêineres:
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

Conclua ou exclua tarefas somente quando o usuário pedir explicitamente:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` salva a captura de tela no disco e ainda escreve JSON no stdout para scripts. Os IDs de captura de tela geralmente vêm de `local search-screen` ou SQL na tabela `screenshots`. Se o Desktop retornar um erro estruturado como `screenshot_pending`, `screenshot_file_missing` ou `screenshot_chunk_corrupted`, o modo JSON preserva os campos `reason`, `hint` e `screenshot_id` no stderr para que os agentes possam tentar novamente com um ID mais antigo ou relatar o obstáculo exato. Verifique os resultados bem-sucedidos com `file PATH` antes de passá-los para ferramentas de visão.

## Exemplo prático: loop de agente Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Execute o CLI omi em modo JSON e lance exceção em códigos de saída ruins."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # O CLI escreve erros estruturados para stderr no modo JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi terminou com o código {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ler todos os itens de ação abertos e marcar como concluídos os mais antigos que 30 dias.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Tratamento de limites de taxa

Memórias: 120/hora. Conversas: 25/hora. Criação em lote: 15/hora.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # limite de taxa atingido
    err = json.loads(result.stderr)
    # err["detail"] parece: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Dicas

* Use `--profile <nome>` se seu agente gerenciar várias contas Omi. Cada perfil tem suas próprias credenciais e base de API.
* Use `--api-base http://localhost:8080` para testes de backend local.
* Use `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` para substituir as configurações da API local do Desktop do perfil para uma única execução.
* Use `--verbose` para depuração — registra `METHOD path → status (Ns)` no stderr sem afetar o stdout, portanto o modo JSON permanece válido.
* Para canalizar conteúdo para uma conversa, use `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
