# omi-cli — guia de início rápido em português

> Guia prático para trabalhar com o Omi a partir do terminal. Adequado tanto para pessoas quanto para agentes de IA.

`omi-cli` é o cliente oficial de linha de comando para a API de desenvolvedor do [Omi](https://omi.me).
Ele oferece acesso rápido e fácil de automatizar às quatro entidades principais do Omi:
memórias, conversas, tarefas e objetivos.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentação:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código-fonte:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalação

O método recomendado é o `pipx`: ele instala a ferramenta num ambiente isolado,
para que as dependências não entrem em conflito com os seus projetos.

```bash
# recomendado: instalação via pipx
pipx install omi-cli

# ou via pip
pip install omi-cli
```

> **Importante: o nome do pacote e o nome do comando são diferentes.**
> * O pacote instalado é **`omi-cli`** (o pacote separado `omi` é outro projeto, sem relação).
> * Após a instalação, você executa o comando **`omi`**.

Verifique se tudo funciona:

```bash
omi --version
omi --help
```

---

## 2. Autenticação

O `omi-cli` suporta duas formas de iniciar sessão.

| Método | Indicado para | Comando |
| :--- | :--- | :--- |
| **Chave de desenvolvedor (`omi_dev_*`)** | CI/CD, scripts, agentes de IA | `omi auth login --api-key ...` ou variável de ambiente |
| **Login pelo navegador (Google/Apple)** | Trabalho no próprio computador | `omi auth login --browser` |

### Login interativo

Sem opções, o comando pergunta qual método você quer usar:

```bash
omi auth login
# 1) Browser — entrar com Google ou Apple (conveniente para pessoas)
# 2) API key — colar a chave de desenvolvedor de app.omi.me (conveniente para agentes e CI)
```

Ao escolher a chave, a entrada é mascarada para que a chave não fique no histórico do terminal.

### Diretamente pelo navegador

```bash
omi auth login --browser
```

### Via chave de desenvolvedor

A chave é obtida em [app.omi.me](https://app.omi.me) em **Developer → API Keys**.

```bash
# guardar a chave na configuração
omi auth login --api-key omi_dev_...

# ou passá-la pelo ambiente — preferido para CI/CD e contentores
export OMI_API_KEY=omi_dev_...
```

A variável de ambiente `OMI_API_KEY` é usada quando não há chave guardada no perfil ativo;
num contentor, nada precisa de ser escrito em disco. Se o perfil já tiver uma chave,
ela tem prioridade sobre a variável de ambiente.

### Verificar o login

Dois comandos respondem a perguntas diferentes e não devem ser confundidos:

* `omi auth status` — o que está guardado **localmente**: perfil, chave mascarada, data de expiração.
  Funciona sem rede.
* `omi auth whoami` — pedido **ao servidor Omi**: verifica que a chave é realmente
  aceite. Requer rede.

```bash
omi auth status    # verificação local, offline
omi auth whoami    # verificação no servidor
```

Renovar um token prestes a expirar sem iniciar sessão novamente — este comando aplica-se
**apenas a sessões de navegador/OAuth**. Num perfil autenticado por chave API (`omi_dev_*`),
`omi auth refresh` falha com um erro de uso (código 1): não há token para renovar —
rode a chave na aplicação web do Omi, se necessário:

```bash
omi auth refresh
```

Terminar sessão:

```bash
omi auth logout
```

---

## 3. Comandos básicos

### Memórias (memories)

Factos e conhecimentos que o sistema guardou sobre si.

```bash
# lista de memórias
omi memory list

# criar uma nova
omi memory create "O utilizador prefere o tema escuro" --category lifestyle

# ver uma em particular
omi memory get <MEMORY_ID>
```

### Conversas (conversations)

Histórico de voz e texto do dispositivo ou da aplicação.

```bash
# as 5 conversas mais recentes
omi conversation list --limit 5

# uma conversa completa com transcrição
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tarefas (action items)

Tarefas que o Omi extraiu das conversas.

```bash
# apenas as abertas
omi action-item list --open

# marcar como concluída
omi action-item complete <ACTION_ITEM_ID>
```

### Objetivos (goals)

```bash
# lista de objetivos
omi goal list

# registar um novo valor de progresso (requer AMBOS os argumentos: objetivo e valor)
omi goal progress <GOAL_ID> 25

# histórico de alterações
omi goal history <GOAL_ID>
```

---

## Fazer perguntas com as suas próprias palavras (`ask`)

Um comando de topo separado: faz uma pergunta em linguagem natural,
e a resposta é construída a partir das suas próprias conversas.

```bash
omi ask "o que decidi sobre a mudança de casa"
omi --json ask "que tarefas prometi fechar esta semana"
```

---

## 4. JSON e scripts (`--json`)

O `omi-cli` pode produzir JSON legível por máquina. A opção `--json` é **global**
e por isso é colocada **antes** do subcomando.

```bash
# memórias: extrair id, texto e categoria
omi --json memory list | jq '.[] | {id, content, category}'

# títulos das conversas recentes
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# tarefas abertas
omi --json action-item list --open | jq '.'
```

> **Erro comum.** `--json` vem antes do subcomando, não depois.
> * Correto: `omi --json memory list`
> * Errado: `omi memory list --json`

No modo `--json`, nada além do próprio JSON é escrito para stdout —
os scripts podem confiar nisso.

---

## 5. Códigos de saída

Os códigos são estáveis, para que a lógica de scripts e CI possa depender deles.

| Código | Significado | Quando |
| :---: | :--- | :--- |
| `0` | Sucesso | O comando foi executado |
| `1` | Erro de invocação | Validação do próprio omi-cli (p. ex. `--browser` e `--api-key` ao mesmo tempo, escolha de login inválida, stdin vazio) |
| `2` | Erro de acesso | Sessão não iniciada, chave inválida ou expirada |
| `3` | Erro de servidor | Resposta 5xx, timeout, sem ligação |
| `4` | Demasiados pedidos | 429 Too Many Requests |
| `5` | Não encontrado | 404, o id não existe |

> **Nota.** Opções desconhecidas e argumentos em falta são apanhados pelo Click e dão o código `2`.

Exemplo de verificação em Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "a chave funciona"
else
  code=$?
  [ "$code" -eq 2 ] && echo "iniciar sessão novamente"
  [ "$code" -eq 3 ] && echo "o servidor está em baixo, tente mais tarde"
fi
```

---

## 6. Variáveis de ambiente

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_a_sua_chave"

omi --json memory list --limit 10
```

Para que a chave seja carregada em novas sessões, adicione a linha a `~/.bashrc` ou `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_a_sua_chave"

# parsing de JSON com PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Para configuração permanente:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_a_sua_chave", "User")
```

---

## 7. A aplicação Omi Desktop em local

Se a aplicação de desktop Omi estiver em execução, parte dos dados fica disponível
diretamente, sem passar pela nuvem.

```bash
# indicar o endereço da API local
omi local configure --url http://127.0.0.1:47778 --token O_SEU_TOKEN

# verificar se responde
omi --json local status

# pesquisa no histórico de ecrã
omi --json local search-screen "preços" --days 7 --app Safari

# captura de ecrã por id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# SQL arbitrário contra a base de dados local
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Fluxo recomendado: primeiro `local status`, depois `local tools` — para ver as
ferramentas disponíveis e os seus parâmetros — e só depois as chamadas.

---

## 8. Perfis

Se tiver várias contas ou ambientes, separe-os com perfis.
As definições são guardadas em `~/.omi/config.toml`.

```bash
# login no perfil pessoal
omi --profile personal auth login

# login no perfil de trabalho
omi --profile work auth login

# executar um comando num perfil específico
omi --profile work memory list
```

O perfil utilizado é determinado nesta ordem: a opção `--profile` (ou `-p`) prevalece
sobre tudo o resto; depois a variável de ambiente `OMI_PROFILE`; depois o perfil ativo
definido em `~/.omi/config.toml`; e, em último caso, o perfil `default`.

Ver e alterar a própria configuração:

```bash
# o que está configurado agora
omi config show

# onde fica o ficheiro de configuração
omi config path

# alterar um valor
omi config set api_base https://api.omi.me
```

---

## 9. Próximos passos

* [`agent_quickstart.md`](./agent_quickstart.md) — como ligar o `omi-cli` a um agente de IA.
* [`shell_examples.sh`](./shell_examples.sh) — exemplos prontos para o shell.
* [Documentação do Omi](https://docs.omi.me/doc/developer/cli/introduction) — a referência completa dos comandos.
