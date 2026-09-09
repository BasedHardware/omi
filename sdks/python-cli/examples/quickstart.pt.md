# Guia de Início Rápido do omi-cli (Quickstart Guide)

> Guia prático para interagir com o Omi direto do seu terminal — desenvolvido para usuários e agentes de IA autônomos.

O `omi-cli` é a interface de linha de comando oficial para a API de desenvolvedor do [Omi](https://omi.me). Ele permite gerenciar de forma estruturada e automatizável os quatro recursos centrais do sistema: memórias (memories), conversas (conversations), tarefas (action items) e metas (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentação Oficial:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código-Fonte:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalação

A forma recomendada de instalação é via `pipx`, que isola as dependências do ambiente do sistema:

```bash
# Recomendado: instalação isolada com pipx
pipx install omi-cli

# Ou via pip tradicional
pip install omi-cli
```

> **Atenção: Nome do pacote vs. Nome do comando**
> * O nome do pacote no PyPI é **`omi-cli`** (o nome `omi` pertence a outro pacote não relacionado).
> * O comando executável disponibilizado no seu terminal é simplesmente **`omi`**.

Valide a instalação consultando a versão e o menu de ajuda:

```bash
omi --version
omi --help
```

---

## 2. Autenticação (Authentication)

O `omi-cli` suporta dois métodos de autenticação:

| Método | Indicado para | Exemplo de uso |
| :--- | :--- | :--- |
| **Chave de API (`omi_dev_*`)** | Automações, CI/CD, servidores headless, agentes de IA | `omi auth login --api-key ...` ou `OMI_API_KEY` |
| **OAuth via Navegador (Google/Apple)** | Desenvolvedores em laptops / máquinas locais | `omi auth login --browser` |

### Login Interativo
Ao rodar sem argumentos adicionais, o assistente pergunta qual fluxo deseja utilizar:

```bash
omi auth login
# 1) Browser — Autenticação via Google ou Apple no navegador web
# 2) API key — Cole sua chave de desenvolvedor gerada no app.omi.me
```

### Login Direto pelo Navegador
```bash
omi auth login --browser
```

### Usando uma Chave de Desenvolvedor (API Key)
Obtenha sua chave no painel do [app.omi.me](https://app.omi.me) em **Developer → API Keys**:

```bash
# Definir permanentemente no perfil local
omi auth login --api-key omi_dev_...

# Ou definir como variável de ambiente (ideal para containers e pipelines de CI)
export OMI_API_KEY="omi_dev_..."
```

### Verificar o Status da Autenticação
* `omi auth status`: Exibe o perfil ativo local, tokens mascarados e datas de expiração (opera offline).
* `omi auth whoami`: Faz uma chamada à API para confirmar se a credencial está válida no servidor (requer conexão).

```bash
omi auth status
omi auth whoami
```

Para encerrar a sessão:
```bash
omi auth logout
```

---

## 3. Comandos Principais

### Memórias (Memories)
Fatos, aprendizados e informações de contexto armazenadas pelo Omi:

```bash
# Listar memórias salvas
omi memory list

# Criar uma nova memória
omi memory create "Prefere respostas técnicas concisas com exemplos em Python" --category work

# Obter detalhes de uma memória específica
omi memory get <MEMORY_ID>
```

### Conversas (Conversations)
Histórico de áudio e texto capturados pelos dispositivos Omi:

```bash
# Listar as 5 conversas mais recentes
omi conversation list --limit 5

# Obter detalhes e o transkript completo da conversa
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tarefas (Action Items)
Itens de ação e pendências geradas automaticamente a partir de conversas:

```bash
# Listar tarefas pendentes
omi action-item list --open

# Concluir uma tarefa
omi action-item complete <ACTION_ITEM_ID>
```

### Metas (Goals)
Acompanhamento de métricas de progresso e objetivos:

```bash
# Listar metas ativas
omi goal list

# Criar uma nova meta quantitativa
omi goal create "Beber 2L de água diariamente" --type numeric --target 2 --unit liters
```

---

## 4. Automação e Saída em JSON (`--json`)

O `omi-cli` oferece suporte nativo de primeira classe a pipelines estruturados. Ao passar a opção global `--json`, os resultados são emitidos em JSON válido:

```bash
# Listar memórias em JSON e extrair campos com jq
omi --json memory list | jq '.[] | {id, content, category}'

# Extrair títulos das últimas conversas
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Consultar tarefas abertas em formato bruto
omi --json action-item list --open | jq '.'
```

> **Regra de sintaxe essencial:**
> O modificador `--json` é uma **opção global** e deve vir **antes** do subcomando:
> * Correto: `omi --json memory list`
> * Incorreto: `omi memory list --json`

---

## 5. Códigos de Saída (Exit Codes)

Para integrações confiáveis em shell scripts e esteiras de CI/CD:

| Código | Significado | Descrição |
| :---: | :--- | :--- |
| `0` | **Sucesso (Success)** | Execução concluída com êxito. |
| `1` | **Erro de Uso (Usage Error)** | Argumentos inválidos, parâmetros ausentes ou sintaxe incorreta. |
| `2` | **Erro de Autenticação (Auth Error)** | Não autenticado, chave inválida ou token expirado. |
| `3` | **Erro de Servidor/Rede (Server Error)** | Resposta HTTP 5xx, timeout ou falha de conexão. |
| `4` | **Limite de Requisições (Rate Limited)** | HTTP 429 Too Many Requests — requisição bloqueada por rate limit. |
| `5` | **Não Encontrado (Not Found)** | HTTP 404 Not Found — o identificador requisitado não existe. |

---

## 6. Exemplos por Ambiente de Shell

### Bash / Zsh (Linux / macOS)
```bash
# Definir credencial na sessão
export OMI_API_KEY="omi_dev_sua_chave_aqui"

# Execução com checagem de código de saída
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Erro ao consultar as memórias do usuário" >&2
fi
```

### PowerShell (Windows)
```powershell
# Definir variável de ambiente no PowerShell
$env:OMI_API_KEY = "omi_dev_sua_chave_aqui"

# Converter a saída JSON diretamente em objetos do PowerShell
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Checagem de erro via $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Comando Omi falhou com o código $LASTEXITCODE"
}
```

---

## 7. Integração com a API Local do Desktop

Quando o aplicativo Omi Desktop está ativo na máquina, o CLI pode consultar capturas de tela e o histórico local sem requisições à nuvem:

```bash
# Configurar o endpoint local
omi local configure --url http://127.0.0.1:47778 --token SEU_TOKEN_DESKTOP

# Verificar a conexão local
omi --json local status

# Buscar na timeline visual recente
omi --json local search-screen "Relatório trimestral" --days 7 --app Safari
```

---

## 8. Gerenciamento de Múltiplos Perfis (Profiles)

Para alternar entre contas pessoais e corporativas ou ambientes de teste, utilize a opção `--profile`. As configurações são persistidas em `~/.omi/config.toml`:

```bash
# Criar e autenticar no perfil pessoal
omi --profile personal auth login

# Criar e autenticar no perfil de trabalho
omi --profile work auth login

# Executar comandos em um perfil específico
omi --profile work memory list
```

---

## 9. Boas Práticas de Segurança

* **Nunca comite chaves no Git:** Armazene suas chaves em gerenciadores de segredos ou arquivos `.env` ignorados pelo `.gitignore`.
* **Histórico do Terminal:** Evite passar segredos como flags diretas em scripts compartilhados. Dê preferência a variáveis de ambiente (`OMI_API_KEY`).
* **Revogação Imediata:** Em caso de exposição acidental, revogue a chave imediatamente no portal [app.omi.me](https://app.omi.me).
