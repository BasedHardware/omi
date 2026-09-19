# Entamar con omi-cli

Esta guía amuesa los primeros comandos n'asturianu. Los nomes de los comandos y los mensaxes del sistema queden n'inglés. Los exemplos de llectura apurríos equí nun van camudar les tos memories, conversaciones, llistes d'aiciones nin oxetivos.

## Instalar el programa

Requisitos: Python 3.10 o una versión más nueva y una cuenta d'Omi.

> Atención: El nome del paquete en PyPI ye **`omi-cli`**, mientres que'l comandu que s'executa dempués d'instalar ye **`omi`**. Hai otru paquete ensin rellación nomáu `omi` en PyPI — nun instales esi paquete.

Si `pipx` ta instaláu:

```sh
pipx install omi-cli
omi --help
```

D'otra miente, dientro d'un entornu virtual de Python activu:

```sh
python -m pip install omi-cli
omi --help
```

Si la terminal nun alcuentra `omi`, asegúrate de que l'entornu virtual tea activu o que'l direutoriu de `pipx` tea nel to `PATH`.

## Coneutar la to cuenta

Entama l'asistente interactivu:

```sh
omi auth login
```

Escueyi aniciar sesión col restolador, o escueyi la opción de pegar una clave API de desendolcador d'Omi. La entrada interactiva anubre la clave; nun escribas la clave en comandos que queden nel historial de la terminal.

P'aniciar sesión direutamente col restolador:

```sh
omi auth login --browser
```

Completa l'aniciu de sesión nel mesmu ordenador onde s'executa la terminal, yá que l'autenticación vuelve a una direición llocal. Sigue les instrucciones na pantalla.

Dempués d'eso, comprueba la configuración y l'accesu a l'API:

```sh
omi auth status
omi auth whoami
```

`status` amuesa l'estáu llocal y anubre los secretos, pero nun los comprueba col sirvidor. `whoami` unvia un pidimientu autenticáu; l'ésitu significa que les tos credenciales funcionen bien.

La configuración guárdase por defeutu en `~/.omi/config.toml`. Nun compartas esti ficheru porque contién les tos credenciales privaes.

## Ver los tos datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una llista balera pue significar cenciellamente que nun hai elementos que concuayen col pidimientu. Pa entender los peñeros d'un comandu, mira l'ayuda:

```sh
omi memory list --help
omi action-item list --help
```

## Consiguir JSON y pasar páxines

Pon la opción global `--json` **enantes** del grupu de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primer comandu pide los primeros 25 rexistros; el segundu pide los 25 siguientes. Por mor d'eso, una páxina nun ye una copia de seguridá completa. La salida JSON caltién los identificadores completos, mientres que les tables puen acurdialos.

Pa guardar una páxina nun ficheru:

```sh
omi --json memory list --limit 25 --offset 0 > memories-paxina-1.json
```

Esti redireccionamientu crea o sustitúi un ficheru llocal. Enantes d'usar el conteníu, asegúrate de que'l comandu tuvo ésitu. Los errores escríbense en stderr; un ficheru baleru nun ye prueba de que nun heba datos. Guarda esti ficheru de mou seguru porque pue contener información personal.

## Zarrar sesión (Log out)

```sh
omi auth logout
```

Esti comandu desanicia les credenciales guardaes llocalmente. Pa revocar una clave nel sirvidor, usa la xestión de claves de desendolcador na to cuenta.

Pa otros comandos y opciones avanzaes, mira la guía principal n'inglés:
[../README.md](../README.md) y `omi --help`.
