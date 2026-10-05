# omi-cli (Português)

[English README](README.md) · [Русский: быстрый старт](README.ru.md) · [日本語 README](README.ja.md) · [Guia de início rápido em português](examples/quickstart.pt.md)

> Converse com o Omi a partir do seu terminal. Projetado para humanos **e** agentes.

`omi-cli` é a interface de linha de comando para a API de desenvolvedores do [Omi](https://omi.me). Ela disponibiliza verbos com escopo definido e adaptados para agentes para os quatro conceitos principais que o Omi mantém sobre você:

* **memórias:** fatos e aprendizados que o sistema sabe sobre você
* **conversas:** trocas de áudio e texto capturadas e processadas
* **itens de ação:** tarefas e acompanhamentos
* **metas:** métricas de progresso acompanhadas

É intencionalmente leve, programável por scripts e orientado a JSON: tudo o que você precisa para conectar o Omi a pipelines de shell, tarefas de CI, ambientes de agentes ou suas próprias automações pessoais.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentação:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código-fonte:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

## Instalação

```bash
pipx install omi-cli            # recomendado: instalação isolada
# ou
pip install omi-cli
```

Após a instalação, o comando no seu `$PATH` é chamado `omi`:

```bash
omi --version
omi --help
```

> O nome de distribuição no PyPI é `omi-cli` (o identificador `omi` pertence a um pacote não relacionado). O comando de console é `omi` de qualquer forma.

## Início rápido

```bash
# 1. Faça login. Sem opções, o omi-cli pergunta como você deseja se autenticar:
omi auth login
# -> 1) Browser: entrar com Google ou Apple (recomendado para humanos)
# -> 2) API key: colar uma chave de desenvolvedor do app.omi.me (recomendado para agentes/CI)

# 2. Comece a usar:
omi memory list
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Passe `--json` para qualquer comando (como opção global, antes do verbo) para obter saída legível por máquina, pronta para `jq`, ambientes de agentes ou qualquer outra ferramenta:

```bash
omi --json memory list | jq '.[] | {id, content}'
```

A saída formatada exibe o texto retornado literalmente, incluindo colchetes e códigos de estilo emoji como `:warning:`. A estilização se aplica ao layout da tabela, não ao conteúdo das suas memórias ou conversas.
Tabelas sem colunas predefinidas incluem campos de cada linha, na ordem em que aparecem pela primeira vez.

> Para guias em outros idiomas, consulte [`examples/README.md`](examples/README.md). O guia rápido em português está disponível em [`examples/quickstart.pt.md`](examples/quickstart.pt.md).

## Autenticação

Dois métodos de autenticação, ambos totalmente integrados:

| Método | Ideal para | Como usar |
| --- | --- | --- |
| Chave de API de desenvolvedor (`omi_dev_*`) | Agentes, CI, ambientes sem interface gráfica, permissões com escopo | `omi auth login --api-key ...` ou variável de ambiente |
| Firebase OAuth (Google/Apple) | Pessoas em computadores pessoais | `omi auth login --browser` |

O fluxo pelo navegador abre seu navegador padrão para OAuth, captura o código em um retorno de chamada em localhost e armazena um token de ID do Firebase mais um token de atualização. O token de ID é atualizado automaticamente antes de cada requisição quando está próximo de expirar: você não precisa se preocupar com isso.

```bash
omi auth login                  # seletor interativo (navegador ou chave)
omi auth login --browser        # forçar OAuth (provedor padrão: google)
omi auth login --browser --provider apple
omi auth login --api-key K      # forçar método de chave de API
omi auth login < key.txt        # chave enviada por pipe, útil em CI
omi auth status                 # exibe perfil, credencial mascarada e expiração
omi auth whoami                 # consulta o servidor para verificar se a credencial funciona
omi auth refresh                # força atualização do Firebase (sem efeito para chaves de API)
omi auth logout                 # remove a credencial
```

As chaves de API são validadas antes de substituir as credenciais salvas. Se a verificação for rejeitada com HTTP 401 ou 403, o perfil existente e a seleção do perfil ativo permanecem inalterados. Outros erros HTTP mantêm o comportamento existente de salvar e emitir aviso. Uma falha de transporte mantém as credenciais salvas inalteradas; o OAuth por navegador é um fluxo separado.

Você também pode definir uma variável de ambiente `OMI_API_KEY` não vazia para substituir a autenticação salva em requisições de API em nuvem: prático em contêineres e CI. A chave é validada mesmo quando o perfil selecionado já possui credenciais; uma substituição inválida falha antes de qualquer requisição à nuvem. Comandos locais do Desktop usam seu token local separado, e `auth status` relata o perfil salvo. Credenciais salvas não são alteradas, e configurações de perfil como a URL base da API continuam aplicáveis:

```bash
export OMI_API_KEY=omi_dev_...
omi memory list
```

## Perfis

O estado fica em `~/.omi/config.toml` (substituível via `$OMI_CONFIG`). O arquivo mantém um ou mais perfis nomeados, cada um com seu próprio método de autenticação e base de API. Salvar a configuração preserva opções desconhecidas nos níveis raiz e de perfil, de forma que editar uma configuração conhecida não descarta extensões adicionadas por clientes mais recentes. Alterne entre perfis com `--profile`:

```bash
omi config profile use work
omi auth login                  # faz login no perfil ativo (work)
omi --profile personal memory list
```

Configurações comuns:

```bash
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
omi config set local_api_url http://127.0.0.1:47778
omi config set local_token ...
omi config profile list
omi config profile delete old-account --yes
```

## API local do Omi Desktop

`omi local` comunica-se com a API local de uma instância em execução do Omi Desktop. Configure o perfil ativo uma vez ou use variáveis de ambiente para sessões efêmeras de agentes:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...
```

Ferramentas locais comuns:

```bash
omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local recap --days-ago 1
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
omi --json local task search "taxes" --include-completed
```

Fluxo de trabalho de histórico de tela para agentes:

1. Verifique a disponibilidade com `omi --json local status`; observe `screen_history_available`, `screenshot_count` e `indexed_screenshot_count`.
2. Descubra os esquemas de ferramentas com `omi --json local tools`.
3. Pesquise no histórico de OCR/tela com `omi --json local search-screen "query" --days 7` ou execute SQL exato em `screenshots` quando precisar de filtros por aplicativo ou janela.
4. Use o `screenshot_id` retornado com `omi --json local screenshot <id> --output /tmp/omi-shot.jpg`.
5. Valide o arquivo antes de enviá-lo para ferramentas de visão computacional, por exemplo com `file /tmp/omi-shot.jpg`.

Quando a pesquisa semântica não retorna resultados, o modo JSON também tenta uma busca literal por substring entre nomes de aplicativo, títulos de janela e texto de OCR. Nesse fallback, `%` e `_` na consulta ou no filtro `--app` correspondem literalmente a esses caracteres em vez de atuar como curingas SQL.

Se os pixels não estiverem disponíveis, os erros em modo JSON preservam os campos estruturados do Desktop como `status_code`, `error`, `reason`, `hint` e `screenshot_id`. Por exemplo, `screenshot_pending` indica que o quadro ainda está no segmento de vídeo ativo; tente novamente em breve ou escolha um ID de captura mais antigo nos resultados de busca.

Gravações em tarefas só devem ser executadas depois que o usuário solicitar claramente essa alteração:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

### Aplicar o intervalo de tempo solicitado à busca exata em tela

O fallback exato por aplicativo, janela e OCR para `omi --json local search-screen` respeita o mesmo intervalo contínuo de `--days` que a busca semântica.

## Estrutura de comandos

A árvore completa (execute `omi --help` para ver a árvore de comandos da versão instalada):

```text
omi
├── auth
│   ├── login [--browser] [--api-key KEY]
│   ├── logout
│   ├── status
│   ├── whoami
│   └── refresh
├── config
│   ├── show
│   ├── path
│   ├── set <key> <value>
│   └── profile
│       ├── list
│       ├── use <name>
│       └── delete <name>
├── memory
│   ├── list [--limit N] [--offset N] [--categories ...]
│   ├── get <id>
│   ├── create <content> [--category ...] [--visibility ...] [--tag ...]
│   ├── update <id> [--content ...] [--category ...] [--visibility ...] [--tag ...]
│   └── delete <id> [-y]
├── conversation
│   ├── list [--limit N] [--start-date ...] [--end-date ...] [--include-transcript]
│   ├── get <id> [--include-transcript]
│   ├── create [--text ...] [--text-source ...] [...]
│   ├── from-segments <file.json> [--source ...]
│   ├── update <id> [--title ...] [--discarded/--no-discarded]
│   └── delete <id> [-y]
├── action-item
│   ├── list [--completed/--open] [--conversation-id ...] [...]
│   ├── get <id>
│   ├── create <description> [--due-at ...]
│   ├── update <id> [--description ...] [--completed/--open] [--due-at ...]
│   ├── complete <id>
│   └── delete <id> [-y]
├── local
│   ├── configure --url URL --token TOKEN
│   ├── status
│   ├── tools
│   ├── call <tool> [--args-json JSON]
│   ├── search-screen <query> [--days N] [--app NAME]
│   ├── screenshot <id> [--output PATH]
│   ├── recap [--days-ago N]
│   ├── sql <query>
│   └── task
│       ├── search <query> [--include-completed]
│       ├── complete <id>
│       └── delete <id> [-y]
└── goal
    ├── list [--limit N] [--include-inactive]
    ├── get <id>
    ├── create <title> --target N [--type ...] [--current N] [--unit ...]
    ├── update <id> [--unit ... | --clear-unit] [...]
    ├── progress <id> <value>
    ├── history <id> [--days N]
    └── delete <id> [-y]
```

`conversation from-segments` lê arquivos JSON como UTF-8 (com ou sem BOM), UTF-16 ou UTF-32, independentemente da codificação padrão do sistema.
Tanto o JSON de transcrições quanto `local call --args-json` exigem números finitos: `NaN`, `Infinity`, `-Infinity` e valores fora do intervalo finito de ponto flutuante do Python são rejeitados antes de abrir um cliente de API. No modo `--json`, esses erros de entrada são relatados como JSON em stderr.

Opções numéricas de metas e valores de progresso também devem ser finitos. `NaN`, infinitos e expoentes com estouro de capacidade são rejeitados antes de emitir uma requisição de API.

`action-item get` pesquisa páginas sucessivas da API até encontrar o ID ou atingir o final dos resultados. Ele pode recuperar itens além dos primeiros 1.000; consultar um item mais antigo ou inexistente pode exigir várias requisições de API.

## Opções globais

```text
--json                 Emite JSON para stdout (legível por máquina, ideal para agentes).
--profile, -p NAME     Usa um perfil específico.
--api-base URL         Sobrescreve a URL base da API.
--verbose, -v          Registra o tráfego HTTP em stderr.
--no-color             Desativa a saída colorida (também respeita $NO_COLOR).
--version              Exibe a versão instalada.
--help                 Exibe a ajuda contextual.
```

## Códigos de saída (contrato estável)

```text
0  sucesso
1  erro de uso (opções inválidas, argumentos ausentes, validação)
2  erro de autenticação (sem credenciais, token expirado, escopo insuficiente)
3  erro de servidor (5xx, falha de conexão)
4  limite de taxa excedido (429): repetição recomendada
5  não encontrado (404)
```

## Para agentes

O CLI foi construído para que um LLM possa usá-lo sem a necessidade de um wrapper:

* `--json` retorna JSON válido para stdout. Nada mais escreve em stdout no modo JSON (erros vão para stderr como `{"error": "...", "detail": "..."}`).
* Use `omi --json version` para obter um objeto de versão legível por máquina (`{"version": "..."}`). `omi version` e a opção direta `omi --version` mantêm sua saída em texto simples.
* Códigos de saída estáveis (acima) permitem que um agente diferencie entre erros passíveis de repetição e erros terminais.
* Comandos bem-sucedidos de `delete --yes` em recursos preservam a resposta da API no modo JSON. Uma resposta bem-sucedida sem corpo é emitida como `null` em JSON.
* Erros de limite de taxa incluem um intervalo `Retry-After` na mensagem e informam o nome da política (`dev:conversations`, etc.) para que o agente possa aguardar de forma inteligente.
* As variáveis de ambiente `OMI_API_KEY` e `OMI_API_BASE` funcionam sem qualquer `auth login` prévio.
* `OMI_LOCAL_API_URL` e `OMI_LOCAL_TOKEN` substituem as configurações locais da API do Desktop do perfil para `omi local`.

Consulte [`examples/agent_quickstart.pt.md`](examples/agent_quickstart.pt.md) (versão em inglês: [`examples/agent_quickstart.md`](examples/agent_quickstart.md)) para ver um exemplo prático.

## Limites de taxa

A API de desenvolvimento aplica limites por hora por política:

| Política | Limite |
| --- | --- |
| `dev:conversations` | 25/hora |
| `dev:memories` | 120/hora |
| `dev:memories_batch` | 15/hora |

O CLI repete requisições com código `429` automaticamente com recuo exponencial e respeita a indicação `Retry-After` do servidor quando presente. Depois que todas as tentativas forem esgotadas, você recebe o código de saída `4` mais uma mensagem informando quanto tempo esperar.

Requisições POST e PATCH não são reenviadas automaticamente após uma falha ambígua de transporte ou erro de servidor: o servidor pode já ter aplicado a gravação. Essas falhas retornam código de saída `3` com mensagem de `outcome unknown`. Verifique o recurso antes de tentar novamente. Falhas de estabelecimento de conexão e respostas de limite de taxa continuam sendo repetidas; repetições de leitura não são alteradas.

## Permitir limpar a data de vencimento de um item de ação

`omi action-item update ID --clear-due-at` remove a data de vencimento em servidores que suportam campos PATCH explicitamente nulos (correção no backend #13029). Não pode ser combinado com `--due-at`. Omitir ambos mantém a data inalterada.

## Preservar a saída ambígua de tabelas SQL

`omi --json local sql` mantém tabelas de exibição ambíguas ou truncadas sob `text` em vez de descartar células silenciosamente. Respostas estruturadas do Desktop são repassadas sem alterações; a exibição em texto não é um formato de rede SQL sem perdas.

## Opções de data e hora

Opções de data e hora para conversas e itens de ação aceitam carimbos de data/hora ISO com `Z` (UTC), deslocamentos numéricos e frações de segundos opcionais, por exemplo `--due-at 2026-09-08T12:30:00Z` ou `--start-date 2026-09-08T12:30:00.123456+05:30`. Deslocamentos são preservados nas requisições à API. Valores contendo apenas data e carimbos de data/hora sem deslocamento continuam suportados; o CLI não atribui um fuso horário a essas entradas.

## Desenvolvimento

```bash
# Instalação editável com dependências de desenvolvimento
pip install -e .[dev]

# Executar a suíte de testes
pytest -q

# Lint
black --check --line-length 120 --skip-string-normalization sdks/python-cli/
mypy omi_cli

# Construir wheel e sdist (sem envio nem criação de tags)
bash release.sh --build-only
```

## Licença

MIT: consulte [`LICENSE`](LICENSE).
