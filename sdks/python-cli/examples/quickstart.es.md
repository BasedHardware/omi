# Primeros pasos con omi-cli

Esta guía explica los primeros comandos en español. Los nombres de los
comandos y los mensajes del programa se mantienen en inglés. Los ejemplos de
consulta que aparecen aquí no modifican tus recuerdos, conversaciones, tareas
ni objetivos.

## Instalar el programa

Requisitos: Python 3.10 o una versión posterior y una cuenta de Omi.

Si tienes `pipx` instalado:

```sh
pipx install omi-cli
omi --help
```

Como alternativa, puedes instalarlo dentro de un entorno virtual de Python
activado:

```sh
python -m pip install omi-cli
omi --help
```

Si el terminal no encuentra `omi`, comprueba que el entorno virtual esté
activado o que el directorio donde `pipx` instala sus ejecutables esté en tu
`PATH`.

## Conectar tu cuenta

Inicia el asistente interactivo:

```sh
omi auth login
```

Elige iniciar sesión en el navegador o la opción de pegar una clave API
de desarrollador de Omi. La entrada interactiva oculta la clave; evita
escribirla en un comando que quedará en el historial del terminal.

Para ir directamente al navegador:

```sh
omi auth login --browser
```

Inicia sesión en el mismo ordenador que el terminal: la respuesta de
autenticación utiliza una dirección local. Sigue las instrucciones que
aparecen en pantalla.

Después, verifica la configuración y el acceso a la API:

```sh
omi auth status
omi auth whoami
```

`status` muestra el estado local y oculta el secreto, pero no comprueba su
validez en el servidor. `whoami` realiza una solicitud autenticada; si tiene
éxito, confirma que las credenciales funcionan, sin mostrar necesariamente tu
nombre.

La configuración se guarda en `~/.omi/config.toml` por defecto. No compartas
este archivo: puede contener tus credenciales.

## Consultar tus datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista vacía puede significar simplemente que no hay elementos que
coincidan con la consulta. Usa la ayuda para descubrir los filtros de cada
comando:

```sh
omi memory list --help
omi action-item list --help
```

## Obtener JSON y navegar por las páginas

Coloca la opción global `--json` **antes** del grupo de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primer comando pide los primeros 25 recuerdos; el segundo, los 25
siguientes. Una sola página no es, por tanto, una copia de seguridad completa.
La salida JSON conserva los identificadores completos, mientras que las tablas
pueden acortarlos para mostrarlos.

Para guardar una página en un archivo:

```sh
omi --json memory list --limit 25 --offset 0 > recuerdos-pagina-1.json
```

Esta redirección crea o reemplaza el archivo local. Comprueba que el comando
terminó correctamente antes de usar su contenido. Los errores se escriben en
la salida de error; un archivo vacío no garantiza que no haya datos. El
archivo exportado puede contener información personal: mantenlo privado.

## Cerrar sesión

```sh
omi auth logout
```

Este comando elimina las credenciales guardadas localmente. Para revocar una
clave en el servidor, usa la gestión de claves de desarrollador de tu cuenta.

Para el resto de comandos y opciones avanzadas, consulta la
[guía principal en inglés](../README.md) y `omi --help`.
