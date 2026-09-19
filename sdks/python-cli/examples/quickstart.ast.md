# Primeiros pasos con omi-cli

Esta guía esplica los primeros comandos n'asturianu. Los nomes de los comandos
y los mensaxes del programa caltiénense n'inglés. Los exemplos d'esta guía nun
modifiquen les tos alcordances, conversaciones, xeres nin oxetivos.

## Instalación del programa

Requisitos: Python 3.10 o posterior y una cuenta d'Omi.

Si tienes `pipx` instaláu:

```sh
pipx install omi-cli
omi --help
```

Tamién pues instalalu nun entornu virtual (virtual environment) activu de Python:

```sh
python -m pip install omi-cli
omi --help
```

Si la terminal nun alcuentra `omi`, asegúrate de que l'entornu virtual tea activu
o de que'l directoriu onde `pipx` instala los executables tea na to variable `PATH`.

## Coneuta la to cuenta

Inicia l'asistente interactivu d'aniciu de sesión:

```sh
omi auth login
```

Escueye aniciar sesión al traviés del restolador (browser) o apega una clave API de
desendolcador d'Omi. La entrada interactiva despinta la clave; evita ponela nun
comandu que pueda quedar nel historial de la terminal.

Pa dir directamente al restolador:

```sh
omi auth login --browser
```

Anicia sesión nel mesmu ordenador onde tea executándose la terminal: la rempuesta
d'autenticación usa una dirección llocal. Sigue les instrucciones de la pantalla.

Dempués, verifica la configuración y l'accesu a l'API:

```sh
omi auth status
omi auth whoami
```

`status` amuesa l'estáu llocal y despinta'l secretu, pero nun comprueba la validez
nel servidor. `whoami` unvia un pidimientu autenticáu; si tien ésitu, confirma que
les credenciales funcionen correutamente ensin amosar necesariamente'l to nome.

La configuración guárdase por defectu en `~/.omi/config.toml`. Nun compartes esti
ficheru: pue contener los tos datos d'accesu confidenciales.

## Esplora los tos datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una llista vacia pue significar cenciellamente que nun hai elementos que coincidan
col pidimientu. Usa l'ayuda pa ver los filtros disponibles pa cada comandu:

```sh
omi memory list --help
omi action-item list --help
```

## Descarga de JSON y paxinación

Pon la opción global `--json` **enantes** del grupu de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primer comandu pide les primeres 25 alcordances; el segundu pide les siguientes 25.
Una sola páxina nun ye una copia de seguridá completa (backup). La salida JSON caltién
los identificadores completos, mientres que les tables de la pantalla pueden acurtialos.

Pa guardar una páxina nun ficheru:

```sh
omi --json memory list --limit 25 --offset 0 > alcordances-paxina-1.json
```

Esta redirección crea o sobrescribe'l ficheru llocal. Asegúrate de que'l comandu
fine ensin errores enantes d'usar el conteníu. Los errores escríbense na salida d'errores
(stderr); un ficheru vaciu nun garantiza que nun heba datos. El ficheru esportáu pue
contener información personal: caltenlu en priváu.

## Zarrar sesión (Logout)

```sh
omi auth logout
```

Esti comandu desanicia les credenciales guardaes llocalmente. Pa revocar una clave
nel servidor, usa la xestión de claves de desendolcador na to cuenta.

Pa otros comandos y opciones avanzaes, consulta
[la guía principal n'inglés](../README.md) y `omi --help`.
