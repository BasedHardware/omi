# Guia de Início Rápido omi-cli (Português)

> Guia prático para interagir com o Omi a partir do terminal. Adequado tanto para pessoas como para agentes de IA.

`omi-cli` é a interface de linha de comando oficial para interagir com as APIs de programador do [Omi](https://omi.me). Trata de forma eficiente e programável os quatro recursos principais do Omi — **memórias, conversas, action items e objetivos**.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentação oficial:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código-fonte:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalação

O método de instalação recomendado é usar `pipx` para isolar as dependências.

```bash
# Recomendado: instalar com pipx
pipx install omi-cli

# Alternativamente, usar pip
pip install omi-cli
```

> **Importante: diferença entre o nome do pacote e o nome do comando**
> * O pacote Python instalado chama-se **`omi-cli`** (o pacote autónomo `omi` é outro pacote não relacionado).
> * O comando executável no terminal após a instalação é **`omi`**.

Após a instalação, verifique a versão e a ajuda.

```bash
omi --version
omi --help
```

---

## 2. Autenticação

O `omi-cli` suporta dois modos de autenticação.

| Modo | Uso recomendado | Comando de exemplo |
| :--- | :--- | :--- |
| **Chave de API de programador (`omi_dev_*`)** | CI/CD, scripts automáticos, agentes de IA | `omi auth login --api-key ...` ou variável de ambiente |
| **OAuth no browser (Google/Apple)** | PC / portátil do programador | `omi auth login --browser` |

### Início de sessão interativo
Sem opções, ser-lhe-á pedido para escolher entre início de sessão no browser ou introdução da chave de API.

```bash
omi auth login
# 1) Browser — inicie sessão com a sua conta Google ou Apple (para pessoas)
# 2) API key — cole a chave de programador de app.omi.me (para agentes/CI)
```

### Início de sessão direto via browser
```bash
omi auth login --browser
```

### Utilização da chave de API
Obtenha a chave de programador em **Developer → API Keys** em [app.omi.me](https://app.omi.me) e, em seguida, configure-a.

```bash
# Definir através do comando
omi auth login --api-key omi_dev_...

# Ou através de variável de ambiente (ideal para CI/CD ou contentores)
export OMI_API_KEY=omi_dev_...
```

### Verificar o estado de autenticação
* `omi auth status`: mostra o perfil local, o token mascarado e a data de expiração (funciona offline).
* `omi auth whoami`: envia um pedido de autenticação real para o servidor Omi (requer ligação de rede).

```bash
omi auth status
omi auth whoami
```

Para terminar a sessão:
```bash
omi auth logout
```

---

## 3. Utilização Básica

Pode listar e gerir os quatro recursos principais do Omi.

### Memórias (Memories)
Gere factos e conhecimentos aprendidos pelo sistema.

```bash
# Listar todas as memórias
omi memory list

# Criar uma nova memória
omi memory create "O utilizador prefere o modo escuro" --category lifestyle

# Mostrar detalhes de uma memória específica
omi memory get <MEMORY_ID>
```

### Conversas (Conversations)
Histórico de áudio ou texto das conversas captadas pelo dispositivo wearable ou pela aplicação.

```bash
# Obter as últimas 5 conversas
omi conversation list --limit 5

# Mostrar detalhes da conversa e transcrição
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Action Items
Tarefas ou itens de seguimento extraídos automaticamente das conversas.

```bash
# Listar apenas os action items em aberto
omi action-item list --open

# Marcar um action item como concluído
omi action-item complete <ACTION_ITEM_ID>
```

### Objetivos (Goals)
Gere objetivos cujo progresso é monitorizado.

```bash
# Listar todos os objetivos
omi goal list
```

---

## 4. Processamento de Scripts e Saída JSON (`--json`)

O `omi-cli` suporta nativamente saída em JSON. Quando o combina com `jq` ou scripts Python, a **opção global** `--json` deve ser colocada antes do subcomando.

```bash
# Obter a lista de memórias em JSON e extrair ID e conteúdo
omi --json memory list | jq '.[] | {id, content, category}'

# Obter os títulos das últimas 5 conversas
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Listar os action items em aberto
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Listar os objetivos
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Diagnóstico da Sessão

Utilize estes dois comandos em conjunto para resolver problemas rapidamente.

```bash
# 1) Verifique primeiro a configuração local
omi auth status

# 2) Confirme com o servidor Omi
omi auth whoami

# 3) Se necessário, reinicie o início de sessão
omi auth login
```

---

## 6. Melhores Práticas

* **Utilize `--json` nos scripts:** Evite a análise de texto livre; confie sempre na saída JSON estruturada.
* **Isole os ambientes com `pipx`:** Evita conflitos de dependências com outros pacotes Python.
* **Não partilhe chaves de API:** As chaves `omi_dev_*` concedem acesso total à conta — guarde-as num gestor de segredos ou em variáveis de ambiente.
* **Termine sessão em dispositivos partilhados:** Utilize `omi auth logout` após sessões em máquinas partilhadas.

---

## 7. Resolução de Problemas

| Sintoma | Causa provável | Solução |
| :--- | :--- | :--- |
| `command not found: omi` | O PATH não contém o diretório bin do pipx | Execute `pipx ensurepath` e reinicie o terminal |
| `401 Unauthorized` | Chave de API inválida ou expirada | Gere uma nova chave em app.omi.me e atualize |
| `connection refused` | Sem acesso de rede ao servidor Omi | Verifique a ligação à Internet e as definições de proxy |
| `permission denied` nos ficheiros de configuração | O diretório de configuração não é gravável | Verifique as permissões de `~/.omi/config.toml` |

---

## 8. Links Rápidos

* Repositório de origem: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Documentação completa: [docs.omi.me](https://docs.omi.me)
* Issues e suporte: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Comunidade Discord: convite disponível através da página inicial do Omi