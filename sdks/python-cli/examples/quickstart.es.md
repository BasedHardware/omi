# Guía de inicio rápido de omi-cli en español

> Guía práctica para interactuar con Omi desde la terminal. Diseñada para humanos y agentes de inteligencia artificial.

`omi-cli` es la interfaz de línea de comandos oficial para la API de desarrolladores de [Omi](https://omi.me). Permite consultar y gestionar de manera eficiente y automatizada los cuatro recursos principales de Omi: memorias, conversaciones, elementos de acción y metas.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentación oficial:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código fuente:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalación

El método de instalación recomendado es mediante `pipx`, que aísla las dependencias del entorno:

```bash
# Recomendado: instalación aislada con pipx
pipx install omi-cli

# O mediante pip estándar
pip install omi-cli
```

> **Importante: Nombre del paquete vs. Nombre del comando**
> * El nombre del paquete en PyPI es **`omi-cli`** (el paquete `omi` aislado pertenece a un proyecto diferente).
> * El comando ejecutable en la terminal tras la instalación es **`omi`**.

Verifique la instalación consultando la versión y la ayuda:

```bash
omi --version
omi --help
```

---

## 2. Autenticación

`omi-cli` admite dos métodos de autenticación:

| Método | Uso recomendado | Ejemplo de comando |
| :--- | :--- | :--- |
| **Clave API de Desarrollador (`omi_dev_*`)** | CI/CD, scripts desatendidos, agentes IA | `omi auth login --api-key ...` o variable de entorno |
| **OAuth en navegador (Google / Apple)** | Usuarios en estaciones de trabajo locales | `omi auth login --browser` |

### Inicio de sesión interactivo
Si ejecuta el comando sin opciones, se abrirá un selector interactivo:

```bash
omi auth login
# 1) Browser — Iniciar sesión con Google o Apple en el navegador (para humanos)
# 2) API key — Pegar una clave de desarrollador de app.omi.me (para agentes/CI)
```

### Inicio de sesión directo en navegador
```bash
omi auth login --browser
```

### Inicio de sesión con clave API
Obtenga su clave en [app.omi.me](https://app.omi.me) bajo la sección «Developer → API Keys»:

```bash
# Configuración mediante comando
omi auth login --api-key omi_dev_...

# O mediante variable de entorno (ideal para contenedores o CI/CD)
export OMI_API_KEY=omi_dev_...
```

### Verificación del estado de autenticación
* `omi auth status`: Muestra el perfil activo, credenciales enmascaradas y expiración (funciona sin conexión).
* `omi auth whoami`: Realiza una petición de prueba a la API de Omi para comprobar que la credencial es válida (requiere red).

```bash
omi auth status
omi auth whoami
```

Para cerrar sesión y eliminar credenciales locales:
```bash
omi auth logout
```

---

## 3. Uso básico

Consulte y gestione los cuatro recursos principales de Omi:

### Memorias (Memories)
Hechos y conocimientos que el sistema ha registrado sobre el usuario.

```bash
# Listar memorias
omi memory list

# Crear una nueva memoria
omi memory create "El usuario prefiere el modo oscuro" --category lifestyle

# Obtener los detalles de una memoria por ID
omi memory get <ID_MEMORIA>
```

### Conversaciones (Conversations)
Historial de intercambios de audio y texto capturados por dispositivos o la app.

```bash
# Listar las 5 conversaciones más recientes
omi conversation list --limit 5

# Ver detalles y transcripción completa de una conversación
omi conversation get <ID_CONVERSACION> --include-transcript
```

### Elementos de acción (Action Items)
Tareas y compromisos detectados automáticamente en las conversaciones.

```bash
# Listar solo las tareas pendientes
omi action-item list --open

# Marcar una tarea como completada
omi action-item complete <ID_ACCION>
```

### Metas (Goals)
Métricas y objetivos en progreso.

```bash
# Listar metas registradas
omi goal list
```

---

## 4. Scripts y salida en formato JSON (`--json`)

`omi-cli` incluye soporte nativo para JSON en todos sus comandos. Para procesar datos con herramientas como `jq` o scripts en Python, proporcione `--json` como **opción global antes del subcomando**:

```bash
# Listar memorias en JSON y filtrar id, contenido y categoría
omi --json memory list | jq '.[] | {id, content, category}'

# Obtener títulos de conversaciones recientes
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Listar tareas pendientes en formato JSON
omi --json action-item list --open | jq '.'
```

> **Consejo:** Asegúrese de colocar `--json` **antes** del subcomando (`memory`, `conversation`, etc.):
> * Correcto: `omi --json memory list`
> * Incorrecto: `omi memory list --json`

---

## 5. Códigos de salida (Exit Codes)

Para su integración en flujos de automatización y CI, `omi-cli` utiliza códigos de salida normalizados:

| Código | Significado | Descripción |
| :---: | :--- | :--- |
| `0` | Éxito (Success) | El comando se ejecutó correctamente |
| `1` | Error de sintaxis o uso (Usage Error) | Argumento o parámetro no válido |
| `2` | Error de autenticación (Auth Error) | No autenticado, clave no válida o token expirado |
| `3` | Error de servidor / red (Server Error) | Respuesta 5xx, tiempo de espera agotado o fallo de conexión |
| `4` | Límite de peticiones (Rate Limited) | HTTP 429 Too Many Requests |
| `5` | Recurso no encontrado (Not Found) | HTTP 404 (ID no existe) |

---

## 6. Variables de entorno según shell

### Bash / Zsh (Linux / macOS)
```bash
# Establecer clave API
export OMI_API_KEY="omi_dev_su_clave_aqui"

# Ejecución con salida JSON
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# Establecer clave API
$env:OMI_API_KEY = "omi_dev_su_clave_aqui"

# Procesar salida JSON en PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. Integración con Desktop API Local

En estaciones de trabajo con la aplicación Omi Desktop activa, puede consultar el historial de pantalla local o bases de datos locales sin depender de la nube:

```bash
# Configurar la dirección y el token local
omi local configure --url http://127.0.0.1:47778 --token SU_TOKEN_DESKTOP

# Verificar estado de conexión
omi --json local status

# Buscar texto en el historial de pantalla
omi --json local search-screen "factura" --days 7 --app Safari
```

---

## 8. Gestión de perfiles (Profiles)

Si utiliza múltiples cuentas o entornos (por ejemplo, personal y profesional), use el modificador `--profile`. La configuración se guarda en `~/.omi/config.toml`:

```bash
# Iniciar sesión en un perfil personal
omi --profile personal auth login

# Iniciar sesión en un perfil de trabajo
omi --profile work auth login

# Ejecutar comandos bajo el perfil deseado
omi --profile work memory list
```
