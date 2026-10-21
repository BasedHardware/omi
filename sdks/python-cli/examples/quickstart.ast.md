# Los primeros pasos con omi-cli

Esta guía esplica los primeros comandos (commands) de omi-cli n'asturianu. Los nomes de los comandos y los mensaxes del programa queden n'inglés. Los exemplos de gueta qu'amuesa equí nun camuden les tos memories, les tos conversaciones, les tos xeres (action items) nin los tos oxetivos (goals).

## Instalación

Necesítase: Python 3.10 o más nuevu, y una cuenta d'Omi.

Si tienes `pipx`:

```sh
pipx install omi-cli
omi --help
```

Tamién lo pues instalar nun entorno virtual de Python activu:

```sh
python -m pip install omi-cli
omi --help
```

Si'l terminal nun alcuentra `omi`, asegúrate de que l'entornu virtual tea activu o de que la carpeta de `pipx` tea en `$PATH`.

## Coneutar la to cuenta

Entama l'asistente interactivu:

```sh
omi auth login
```

Escueye entrar pel navegador o pegar una clave API de desendolcador d'Omi. La entrada interactiva anubre la clave; evita escribila nun comandu que quede nel historial del terminal.

Pa dir directo al navegador:

```sh
omi auth login --browser
```

Entra nel mesmu ordenador que'l terminal: la respuesta d'autenticación va a la direición llocal. Sigue les instrucciones na pantalla.

Depués, verifica la configuración y l'accesu API:

```sh
omi auth status
omi auth whoami
```

`status` amuesa l'estáu llocal y anubre'l secretu, pero nun verifica la validez nel sirvidor. `whoami` fai una petición autenticada; si funciona, ta claro que les credenciales funcionen, ensin amosar el to nome.

La configuración guárdase por defectu en `~/.omi/config.toml`. Nun compartas esti ficheru: pue contener credenciales privaes.

## Esplorar los tos datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una llista balera normalmente solo significa que nada coincide cola gueta. Usa l'ayuda pa topar los filtros de cada comandu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON y páxines

Pon la opción global `--json` **enantes** del grupu de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primer comandu pide les primeres 25 memories; el segundu les 25 siguientes. Una páxina sola nun ye una copia completa. La salida JSON conserva los númberos enteros, mentanto les tables na pantalla puen acurtialos.

Pa guardar una páxina nun ficheru:

```sh
omi --json memory list --limit 25 --offset 0 > memories-paxina-1.json
```

Esta redireición crea o sobrescribe un ficheru llocal. Asegúrate de que'l comandu acabó enantes d'usar el conteníu. Los errores escríbense na salida d'error (stderr); un ficheru baleru nun ye prueba de que nun haya datos. Un ficheru esportáu pue contener información personal: guárdalu priváu.

## Salir

```sh
omi auth logout
```

Esti comandu borra les credenciales guardaes llocalmente. Pa invalidar una clave nel sirvidor, usa la xestión de claves de desendolcador na to propia cuenta.

Pa más comandos y opciones, mira la [guía principal n'inglés](../README.md) y `omi --help`.
