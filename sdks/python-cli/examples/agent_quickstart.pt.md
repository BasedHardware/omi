# omi-cli para Agentes de IA

> Guia prático para ambientes orientados a LLM (Claude Code, Cursor, bots customizados).

## Por que a CLI é Amigável para Agentes

* **Contrato JSON Estável.** A flag `--json` emite JSON válido para stdout e *apenas* JSON — sem logs de status ou spinners. Erros saem em stderr no formato `{"error": "...", "detail": "..."}`.
* **Códigos de Saída Estáveis.** `0` ok / `1` erro de uso / `2` erro de autenticação / `3` erro de servidor / `4` limite de taxa excedido / `5` não encontrado. Agentes podem ramificar logicamente por código de saída sem regex em mensagens em linguagem natural.
* **Sem Prompts Interativos em Modo Headless.** Passe `--yes` (ou `-y`) para comandos destrutivos; passe `--api-key` ou defina `OMI_API_KEY` para evitar login interativo via navegador.
* **Comportamento de Retry Resiliente.** Respostas `429` e `5xx` realizam tentativas automáticas com backoff exponencial antes de propagar falhas.

## Autenticação (Etapa Única Humana)

O usuário obtém uma chave de API de desenvolvedor no app web Omi
(`https://app.omi.me` → Developer → API Keys) e executa:

```bash
omi auth login                          # colar interativo; a chave não vaza no histórico da shell
# ou
export OMI_API_KEY=omi_dev_...          # efêmero, ideal para contêineres e CI/CD
```

## As Cinco Ações Mais Comuns de Agentes

### 1. Ler Memórias

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Criar uma Memória

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ler Conversas

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ler Itens de Ação Pendentes

```bash
omi action-item list --json --open
```

### 5. Concluir um Item de Ação

```bash
omi action-item complete --json a1b2c3d4
```

## API Local de Desktop (Local Desktop API)

Quando o Omi Desktop expõe sua API local, os agentes podem consultar o histórico de tela do dispositivo, resumos, SQL e tarefas sem usar a API em nuvem:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ou em sessões efêmeras:
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

Conclua ou exclua tarefas somente quando solicitado explicitamente pelo usuário:

```bash
omi --json local task complete task_1
```
