# omi-cli (Español)

[English README](README.md) · [Русский: быстрый старт](README.ru.md) · [日本語 README](README.ja.md) · [Guía de inicio rápido en español](examples/quickstart.es.md)

> Interactúa con Omi desde tu terminal. Diseñado para humanos **y** agentes.

`omi-cli` es la interfaz de línea de comandos para la API de desarrolladores de [Omi](https://omi.me). Expone verbos acotados y adaptados para agentes para los cuatro conceptos principales que Omi mantiene sobre ti:

* **memorias:** hechos y aprendizajes que el sistema conoce sobre ti
* **conversaciones:** intercambios de audio y texto capturados y procesados
* **ítems de acción:** tareas y seguimientos
* **objetivos:** métricas de progreso rastreadas

Está diseñado intencionalmente para ser liviano, programable en scripts y orientado a JSON: todo lo que necesitas para conectar Omi en pipelines de shell, tareas de CI, entornos de agentes o tus propias automatizaciones personales.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentación:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Código fuente:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

## Instalación

```bash
pipx install omi-cli            # recomendado: instalación aislada
# o bien
pip install omi-cli
```

Después de la instalación, el comando en tu `$PATH` se llama `omi`:

```bash
omi --version
omi --help
```

> El nombre de distribución en PyPI es `omi-cli` (el nombre `omi` pertenece a un paquete no relacionado). El comando en la consola es `omi` en cualquier caso.

## Inicio rápido

```bash
# 1. Iniciar sesión. Sin opciones, omi-cli pregunta el método de autenticación:
omi auth login
# -> 1) Browser: iniciar sesión con Google o Apple (recomendado para humanos)
# -> 2) API key: pegar una clave de desarrollador desde app.omi.me (recomendado para agentes/CI)

# 2. Comenzar a usarlo:
omi memory list
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Agrega `--json` a cualquier comando (como opción global, antes del verbo) para obtener salida procesable por máquina, lista para `jq`, entornos de agentes o cualquier otra herramienta:

```bash
omi --json memory list | jq '.[] | {id, content}'
```

La salida con formato muestra el texto recibido de forma literal, incluyendo corchetes y códigos de estilo emoji como `:warning:`. El estilo se aplica al diseño de la tabla, no al contenido de tus memorias o conversaciones.
Las tablas sin columnas predefinidas incluyen campos de cada fila, en orden de primera aparición.

> Para guías en otros idiomas, consulta [`examples/README.md`](examples/README.md). La guía rápida en español está disponible en [`examples/quickstart.es.md`](examples/quickstart.es.md).

## Autenticación

Dos métodos de autenticación, ambos completamente integrados:

| Método | Ideal para | Modo de uso |
| --- | --- | --- |
| Clave API de desarrollador (`omi_dev_*`) | Agentes, CI, entornos sin interfaz gráfica, permisos acotados | `omi auth login --api-key ...` o variable de entorno |
| Firebase OAuth (Google/Apple) | Personas en computadoras personales | `omi auth login --browser` |

El flujo por navegador abre tu navegador predeterminado para OAuth, captura el código en una devolución de llamada en localhost y almacena un token de ID de Firebase junto con un token de actualización. El token de ID se actualiza automáticamente antes de cada solicitud cuando está próximo a expirar: no tienes que preocuparte por ello.

```bash
omi auth login                  # selector interactivo (navegador o clave)
omi auth login --browser        # forzar OAuth (proveedor predeterminado: google)
omi auth login --browser --provider apple
omi auth login --api-key K      # forzar método de clave API
omi auth login < key.txt        # clave enviada por tubería, útil en CI
omi auth status                 # mostrar perfil, credencial enmascarada y expiración
omi auth whoami                 # consulta al servidor para verificar si la credencial funciona
omi auth refresh                # forzar actualización de Firebase (sin efecto para claves API)
omi auth logout                 # eliminar la credencial
```

Las claves de API ingresadas se validan antes de reemplazar las credenciales guardadas. Si la verificación es rechazada con HTTP 401 o 403, el perfil existente y la selección de perfil activo permanecen sin cambios. Otros errores HTTP mantienen el comportamiento previo de guardar y advertir. Una falla de transporte deja las credenciales guardadas intactas; OAuth por navegador es un flujo independiente.

También puedes definir una variable de entorno `OMI_API_KEY` no vacía para anular la autenticación guardada en solicitudes a la API en la nube: muy práctico en contenedores y CI. La clave se valida incluso cuando el perfil seleccionado ya tiene credenciales; una anulación no válida falla antes de realizar cualquier solicitud a la nube. Los comandos locales de Desktop usan su token local independiente, y `auth status` informa el perfil guardado. Las credenciales guardadas no se modifican, y las configuraciones de perfil como la URL base de la API siguen vigentes:

```bash
export OMI_API_KEY=omi_dev_...
omi memory list
```

## Perfiles

El estado reside en `~/.omi/config.toml` (anulable mediante `$OMI_CONFIG`). El archivo contiene uno o más perfiles con nombre, cada uno con su propio método de autenticación y base de API. Guardar la configuración preserva las opciones desconocidas tanto en el nivel raíz como en el nivel de perfil, por lo que editar una opción conocida no descarta extensiones añadidas por clientes más modernos. Cambia de perfil con `--profile`:

```bash
omi config profile use work
omi auth login                  # inicia sesión en el perfil activo (work)
omi --profile personal memory list
```

Configuraciones habituales:

```bash
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
omi config set local_api_url http://127.0.0.1:47778
omi config set local_token ...
omi config profile list
omi config profile delete old-account --yes
```

## API local de Omi Desktop

`omi local` se comunica con la API local de una instancia activa de Omi Desktop. Configura el perfil activo una sola vez o usa variables de entorno para sesiones efímeras de agentes:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...
```

Herramientas locales habituales:

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

Flujo de trabajo para agentes en el historial de pantalla:

1. Verifica la disponibilidad con `omi --json local status`; busca `screen_history_available`, `screenshot_count` y `indexed_screenshot_count`.
2. Descubre los esquemas de herramientas con `omi --json local tools`.
3. Busca en el historial de OCR/pantalla con `omi --json local search-screen "query" --days 7` o ejecuta consultas SQL exactas sobre `screenshots` cuando requieras filtros por aplicación o ventana.
4. Usa el `screenshot_id` devuelto con `omi --json local screenshot <id> --output /tmp/omi-shot.jpg`.
5. Valida el archivo antes de enviarlo a herramientas de visión artificial, por ejemplo con `file /tmp/omi-shot.jpg`.

Cuando la búsqueda semántica no devuelve resultados, el modo JSON también intenta una búsqueda literal por subcadena en nombres de aplicación, títulos de ventana y texto OCR. En este mecanismo alternativo, `%` y `_` en la consulta o en el filtro `--app` coinciden literalmente con dichos caracteres en lugar de actuar como comodines SQL.

Si los píxeles de imagen no están disponibles, los errores en modo JSON conservan los campos estructurados de Desktop como `status_code`, `error`, `reason`, `hint` y `screenshot_id`. Por ejemplo, `screenshot_pending` indica que el cuadro todavía se encuentra en el segmento activo de video; vuelve a intentar brevemente o selecciona un ID de captura anterior en los resultados de búsqueda.

Las escrituras en tareas solo deben ejecutarse después de que el usuario haya solicitado explícitamente dicho cambio:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

### Aplicar el intervalo de tiempo solicitado a la búsqueda exacta en pantalla

El mecanismo de búsqueda exacta por aplicación, ventana y OCR para `omi --json local search-screen` respeta el mismo intervalo móvil `--days` que la búsqueda semántica.

## Árbol de comandos

El árbol completo (ejecuta `omi --help` para ver el árbol de comandos de la versión instalada):

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

`conversation from-segments` lee archivos JSON codificados en UTF-8 (con o sin BOM), UTF-16 o UTF-32, independientemente de la codificación predeterminada del sistema.
Tanto el JSON de transcripciones como `local call --args-json` requieren números finitos: `NaN`, `Infinity`, `-Infinity` y valores fuera del rango finito de punto flotante de Python son rechazados antes de abrir un cliente de API. En modo `--json`, estos errores de entrada se informan en formato JSON en stderr.

Las opciones numéricas y los valores de progreso para objetivos también deben ser finitos. `NaN`, infinitos y exponentes con desbordamiento se rechazan antes de emitir una solicitud de API.

`action-item get` busca páginas sucesivas de la API hasta encontrar el ID o llegar al final de los resultados. Puede recuperar elementos más allá de los primeros 1.000; localizar un elemento antiguo o inexistente puede requerir varias solicitudes a la API.

## Opciones globales

```text
--json                 Emite JSON a stdout (procesable por máquina, ideal para agentes).
--profile, -p NAME     Usa un perfil específico.
--api-base URL         Sobrescribe la URL base de la API.
--verbose, -v          Registra el tráfico HTTP en stderr.
--no-color             Desactiva la salida con color (también respeta $NO_COLOR).
--version              Muestra la versión instalada.
--help                 Muestra la ayuda contextual.
```

## Códigos de salida (contrato estable)

```text
0  éxito
1  error de uso (opciones no válidas, argumentos faltantes, validación)
2  error de autenticación (sin credenciales, token expirado, permisos insuficientes)
3  error de servidor (5xx, falla de conexión)
4  límite de tasa excedido (429): reintento recomendado
5  no encontrado (404)
```

## Para agentes

El CLI está construido para que un LLM pueda usarlo sin necesidad de un contenedor adicional:

* `--json` devuelve JSON válido en stdout. Nada más escribe en stdout en modo JSON (los errores van a stderr como `{"error": "...", "detail": "..."}`).
* Usa `omi --json version` para obtener un objeto de versión legible por máquina (`{"version": "..."}`). `omi version` y la opción directa `omi --version` mantienen su salida en texto plano.
* Los códigos de salida estables (mencionados arriba) permiten que el agente distinga entre errores reintentables y terminales.
* Los comandos exitosos de `delete --yes` sobre recursos preservan la respuesta de la API en modo JSON. Una respuesta exitosa sin cuerpo se emite como `null` en JSON.
* Los errores por límite de tasa incluyen un intervalo `Retry-After` en el mensaje y exponen el nombre de la política (`dev:conversations`, etc.) para que el agente aplique pausas de forma inteligente.
* Las variables de entorno `OMI_API_KEY` y `OMI_API_BASE` funcionan sin requerir un `auth login` previo.
* `OMI_LOCAL_API_URL` y `OMI_LOCAL_TOKEN` anulan las configuraciones de la API local de Desktop del perfil para `omi local`.

Consulta [`examples/agent_quickstart.es.md`](examples/agent_quickstart.es.md) (versión en inglés: [`examples/agent_quickstart.md`](examples/agent_quickstart.md)) para ver un ejemplo detallado.

## Límites de tasa

La API de desarrolladores aplica límites por hora según la política:

| Política | Límite |
| --- | --- |
| `dev:conversations` | 25/hora |
| `dev:memories` | 120/hora |
| `dev:memories_batch` | 15/hora |

El CLI reintenta automáticamente las respuestas `429` aplicando retroceso exponencial y respetando la indicación `Retry-After` del servidor si está disponible. Una vez agotados los reintentos, devuelve el código de salida `4` junto con un mensaje que indica cuánto tiempo esperar.

Las solicitudes POST y PATCH no se reintentan automáticamente tras una falla ambigua de transporte o un error de servidor: el servidor podría haber aplicado la modificación. Estas fallas devuelven el código de salida `3` con un mensaje de `outcome unknown`. Verifica el recurso antes de volver a intentar. Las fallas al establecer la conexión y las respuestas de límite de tasa continúan reintentándose; los reintentos de lectura no cambian.

## Permitir limpiar la fecha límite de un ítem de acción

`omi action-item update ID --clear-due-at` elimina la fecha límite en servidores que admiten campos PATCH nulos explícitos (corrección de backend #13029). No se puede combinar con `--due-at`. Omitir ambos deja la fecha intacta.

## Preservar la salida ambigua de tablas SQL

`omi --json local sql` conserva las tablas visuales ambiguas o truncadas dentro de `text` en lugar de omitir celdas silenciosamente. Las respuestas estructuradas de Desktop se transmiten sin cambios; la presentación en texto no constituye un formato de red SQL sin pérdidas.

## Opciones de fecha y hora

Las opciones de fecha y hora para conversaciones e ítems de acción aceptan marcas de tiempo ISO con `Z` (UTC), desplazamientos numéricos y fracciones de segundo opcionales, por ejemplo `--due-at 2026-09-08T12:30:00Z` o `--start-date 2026-09-08T12:30:00.123456+05:30`. Los desplazamientos se conservan en las solicitudes a la API. Los valores que solo contienen fecha y las marcas de tiempo sin desplazamiento siguen siendo compatibles; el CLI no asigna una zona horaria a dichas entradas.

## Desarrollo

```bash
# Instalación editable con dependencias de desarrollo
pip install -e .[dev]

# Ejecutar la suite de pruebas
pytest -q

# Análisis estático y formato
black --check --line-length 120 --skip-string-normalization sdks/python-cli/
mypy omi_cli

# Construir wheel y sdist (sin subir ni crear etiquetas)
bash release.sh --build-only
```

## Licencia

MIT: consulta [`LICENSE`](LICENSE).
