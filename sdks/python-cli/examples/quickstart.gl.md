# Guía de inicio rápido de omi-cli (Galician Quickstart)

> Guía práctica para interactuar con Omi directamente dende o terminal — deseñado para desenvolvedores humanos e axentes autónomos de IA.

`omi-cli` é a interface de liña de comandos oficial para a API de desenvolvedores de [Omi](https://omi.me). Proporciona acceso estruturado e optimizado para axentes aos catro recursos principais de Omi: **memorias** (memories), **conversas** (conversations), **tarefas/accións** (action items) e **obxectivos** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentación oficial:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código fonte:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalación

Para evitar conflitos de dependencias e manter un contorno illado, recoméndase instalar mediante `pipx`:

```bash
# Método recomendado: instalación illada con pipx
pipx install omi-cli

# Instalación alternativa con pip estándar (ex. nun contorno virtual)
pip install omi-cli
```

> **Distinción importante: nome do paquete fronte ao comando**
> * O paquete en PyPI chámase **`omi-cli`** (o paquete `omi` é un proxecto diferente e non relacionado).
> * O comando executable dispoñible no teu `$PATH` é directamente: **`omi`**.

Comproba que a instalación é correcta consultando a versión e a axuda xeral:

```bash
omi --version
omi --help
```

---

## 2. Autenticación (Authentication)

`omi-cli` admite dous métodos principais de inicio de sesión:

| Método | Casos de uso | Comando / Configuración |
| :--- | :--- | :--- |
| **Chave de API (`omi_dev_*`)** | CI/CD, servidores headless, automatizacións, axentes de IA | `omi auth login --api-key ...` ou variable `OMI_API_KEY` |
| **OAuth mediante navegador (Google/Apple)** | Desenvolvemento local interactivo no teu equipo persoal | `omi auth login --browser` (Google) / `--provider apple` |

### Inicio de sesión interactivo
Se executas o comando sen argumentos adicionais, abrirase un menú interactivo:

```bash
omi auth login
# 1) Browser — Inicio con Google mediante o navegador (engade `--provider apple` para Apple)
# 2) API key — Introducir unha chave de API xerada en app.omi.me
```

### Inicio de sesión directo con navegador
```bash
# Inicio estándar con conta de Google
omi auth login --browser

# Inicio alternativo con ID de Apple
omi auth login --browser --provider apple
```

### Inicio de sesión con chave de API
Obtén a túa chave dende o panel de control de [app.omi.me](https://app.omi.me) na sección **Developer → API Keys** (prefizo `omi_dev_*`):

```bash
# Gardar a chave no perfil local activo
omi auth login --api-key omi_dev_o_teu_token_aqui

# Ou mediante variable de contorno (ideal para contedores Docker e scripts automatizados)
# Nota: se o perfil activo xa ten unha chave gardada no disco, executa primeiro `omi auth logout`.
export OMI_API_KEY="omi_dev_o_teu_token_aqui"
```

> **Nota sobre `omi auth refresh`:** A renovación de credenciais mediante `omi auth refresh` só é aplicable a sesións OAuth do navegador. Nos perfís baseados en chaves de API, as chaves son estáticas e executar este comando produce un erro de uso (`UsageError`, código de saída 1) coa mensaxe *"Nothing to refresh"* (para actualizar ou rotar chaves de API, xéraas de novo no panel web de Omi).

### Verificación do estado da sesión
* `omi auth status`: Comproba localmente a presenza de credenciais no perfil activo sen chamadas de rede (funciona sen conexión).
* `omi auth whoami`: Realiza unha chamada en tempo real á API de Omi para validar que a sesión e os permisos son correctos.

```bash
omi auth status
omi auth whoami
```

### Pechar sesión (Logout)
```bash
omi auth logout
# Se definiches a variable de contorno OMI_API_KEY, elimínaa da sesión actual:
unset OMI_API_KEY
```

---

## 3. Comandos principais

### Memorias (Memories)
Feitos, notas contextuais e aprendizaxes que Omi rexistrou sobre ti:

```bash
# Listar as memorias almacenadas
omi memory list

# Crear unha nova memoria cunha categoría
omi memory create "Prefire explicacións técnicas concisas e exemplos en Python" --category work

# Obter o detalle dunha memoria polo seu identificador
omi memory get <ID_DA_MEMORIA>
```

### Conversas (Conversations)
Intercambios de voz e transcricións procesados polos dispositivos Omi:

```bash
# Listar as últimas 5 conversas
omi conversation list --limit 5

# Obter unha conversa incluíndo a transcrición completa
omi conversation get <ID_DA_CONVERSA> --include-transcript
```

### Tarefas e accións (Action Items)
Compromisos e tarefas detectados automaticamente a partir dos diálogos:

```bash
# Listar as tarefas pendentes
omi action-item list --open

# Marcar unha tarefa como completada
omi action-item complete <ID_DA_TAREFA>
```

### Obxectivos (Goals)
Métricas de seguimento e obxectivos de progreso persoal:

```bash
# Listar os obxectivos actuais
omi goal list

# Crear un obxectivo numérico
omi goal create "Beber 2 litros de auga ao día" --type numeric --target 2 --unit liters

# Actualizar o progreso dun obxectivo
omi goal progress <ID_DO_OBXECTIVO> 1
```

---

## 4. Automatización estruturada e saída JSON (`--json`)

`omi-cli` está deseñado para integrarse con facilidade en scripts e canalizacións de datos. O modificador global `--json` produce unha saída estruturada que se pode filtrar con ferramentas como `jq`:

```bash
# Listar memorias en formato JSON e extraer campos clave
omi --json memory list | jq '.[] | {id, content, category}'

# Obter títulos e datas das conversas recentes
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Consultar tarefas abertas en JSON cru
omi --json action-item list --open | jq '.'
```

> **Regra fundamental de localización do parámetro:**
> `--json` é unha opción **global**, polo que debe situarse **antes** do subcomando:
> * Correcto: `omi --json memory list`
> * Incorrecto: `omi memory list --json`

### Paxinación e exportación de datos
Podes controlar o volume de rexistros mediante `--limit` e `--offset`:

```bash
# Paxinar resultados cara a arquivos locais
omi --json memory list --limit 25 --offset 0 > memorias_px1.json
omi --json memory list --limit 25 --offset 25 > memorias_px2.json
```

---

## 5. Códigos de saída (Exit Codes)

Contrato formal de códigos de retorno segundo `omi_cli/errors.py` para control de fluxo en scripts:

| Código | Nome canónico | Causa e comportamento |
| :---: | :--- | :--- |
| `0` | `EXIT_OK` | Execución completada con éxito. |
| `1` | `EXIT_USAGE` | Erro de validación propio de `omi-cli` (ex. `--browser` e `--api-key` simultáneos, valores inválidos). *(Nota: argumentos descoñecidos de Click xeran código 2).* |
| `2` | `EXIT_AUTH` | Fallo de autenticación, chave/token ausente ou inválido, ou erro de análise de argumentos de Click. |
| `3` | `EXIT_SERVER` | Erro no servidor da API (HTTP 5xx) ou fallo de rede (resultado incerto en escrituras). |
| `4` | `EXIT_RATE_LIMIT` | Límite de peticións excedido (HTTP 429; o cliente reintenta respectando `Retry-After`). |
| `5` | `EXIT_NOT_FOUND` | Recurso solicitado non atopado na API (HTTP 404). |

---

## 6. Exemplos de scripting en diferentes terminais

### Bash / Zsh (Linux e macOS)
```bash
export OMI_API_KEY="omi_dev_o_teu_token_aqui"

# Executar comando e validar o código de saída
omi --json memory list --limit 10
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Memorias obtidas con éxito."
elif [ $EXIT_CODE -eq 2 ]; then
    echo "Erro de autenticación: comproba OMI_API_KEY ou inicia sesión de novo." >&2
else
    echo "A chamada fallou co código: $EXIT_CODE" >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_o_teu_token_aqui"

# Converter a saída JSON directamente nun obxecto PowerShell
$memorias = omi --json memory list | ConvertFrom-Json
$memorias | Select-Object id, content, category

# Comprobar o código de saída coa variable automática $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "O comando de Omi fallou con código de saída: $LASTEXITCODE"
}
```

---

## 7. Integración coa API local de escritorio (Local Desktop API)

Se tes a aplicación de escritorio Omi en execución no mesmo equipo, podes consultar a cronoloxía da pantalla localmente sen pasar pola nube:

```bash
# Configurar o URL e token local
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Introduce o token local do escritorio: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Verificar o estado do servizo local
omi --json local status

# Buscar na actividade recente da pantalla
omi --json local search-screen "Informe mensual" --days 3 --app Chrome
```

---

## 8. Xestión de múltiples perfís (Profiles)

O parámetro `--profile` permite manter perfís separados (ex. persoal, laboral, contorno de probas). A configuración gárdase en `~/.omi/config.toml`:

```bash
# Iniciar sesión en perfís separados
omi --profile persoal auth login
omi --profile traballo auth login

# Executar consultas baixo un perfil concreto
omi --profile traballo memory list

# Conectar co contorno de probas (staging)
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Seguridade e recomendacións

* **Non comprometas chaves en repositorios:** Nunca inclúas chaves `omi_dev_*` en ficheiros baixo control de versións Git; utiliza variables de contorno ou xestores de segredos.
* **Permisos de ficheiro en sistemas Unix:** Protexe o directorio de configuración local aplicando permisos restrictivos:
  ```bash
  chmod 700 ~/.omi
  ```
* **Limpeza de credenciais temporais:** Ao rematar sesións en máquinas compartidas ou contornas de traballo compartidas, desactiva a variable de contorno con `unset OMI_API_KEY` e pecha a sesión con `omi auth logout`.
