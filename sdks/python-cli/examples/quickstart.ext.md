# Los primerus pasus con omi-cli

Esta guía esplica los primerus comándus (commands) de omi-cli n'estremeñu. Los nombris de los comándus i los mensagis del programa quedan n'ingrés. Los ejemplus de busca qu'apaecin aquí no camudan las tus memórias (memories), las tus conversacionis (conversations), las tus tareas (action items) ni los tus ojetivus (goals).

## Instalación

Mester: Python 3.10 o mas nuevu, i una cuenta Omi.

Si tienis `pipx`:

```sh
pipx install omi-cli
omi --help
```

Tamién puis instalalu nun entornu virtual de Python ativu:

```sh
python -m pip install omi-cli
omi --help
```

Si el terminal no alcuentra `omi`, aseguraté de que l'entornu virtual esté ativu o de que la carpetina de `pipx` esté nel `$PATH`.

## Conetar la tu cuenta

Encetai l'asistenti interactivu:

```sh
omi auth login
```

Escogi entrá pol navegaol o pegandu una llavi API de desarrollaol Omi. La entrá interactiva escuendi la llavi; evita escribila nun comándu que quedi nel estorial del terminal.

Pa dir direutamente al navegaol:

```sh
omi auth login --browser
```

Entra nel mesmu ordenaol que el terminal: la respuesta d'autenticación va a la direción local. Sigue las instrucionis ena pantalla.

Endespués, verifica la configuración i el accesu API:

```sh
omi auth status
omi auth whoami
```

`status` amuestra el estau local i escuendi el segretu, pero no verifica la validez nel serviol. `whoami` fai una petición autenticada; si funciona, está claru que las credencialis funcionan, sin amostrar el tu nombri.

La configuración se guarda por defeutu en `~/.omi/config.toml`. No compartas esti ficheru: puei tenel credencialis privadas.

## Esprorar los tus datus

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista vacía normalmenti solu significat que naide correspondi cona busca. Usa l'ayuda pa alcontrar los filtros de cada comándu:

```sh
omi memory list --help
omi action-item list --help
```

## JSON i páginas

Pon l'opción global `--json` **antis** del grupu de comándus:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primel comándu pidi las primeras 25 memórias; el segundu las 25 siguientis. Una página sola no es una copia completa. La salida JSON conserva los númirus enterus, mentris que las tablas ena pantalla puein acortalus.

Pa guardal una página nun ficheru:

```sh
omi --json memory list --limit 25 --offset 0 > memórias-página-1.json
```

Esta redireción cria o sobrescribi un ficheru local. Aseguraté de que el comándu acaberuni antis d'usar el conteníu. Los erruris s'escribin ena salida d'errur (stderr); un ficheru vacíu no es una prueba de que no aiga datus. Un ficheru esportau puei tenel información personal: guárdalu privau.

## Salir

```sh
omi auth logout
```

Esti comándu borra las credencialis guardás localmenti. Pa invalidal una llavi nel serviol, usa la gestión de llavis de desarrollaol ena tu propia cuenta.

Pa mas comándus i opcionis, mira la [guía prencipal n'ingrés](../README.md) i `omi --help`.
