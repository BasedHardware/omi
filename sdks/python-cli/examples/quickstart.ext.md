# Primerus passus con omi-cli

Esta guía muestra los primerus mandaus d'omi-cli n'estremeñu. Los nombris de los mandaus i los mensahis del programu siguen n'inglés. Los ehemprus d'esta guía nu cambean tus recuerdus, conversacionis, elementus d'ación u ohetivus.

## Estalación

Necesitas Python 3.10 u posterior, i una cuenta Omi.

Si `pipx` ya está instalau:

```sh
pipx install omi-cli
omi --help
```

D'otra manera, pués instalalu nuna entornu virtual de Python activu:

```sh
python -m pip install omi-cli
omi --help
```

Si'l terminal nu alcuentra `omi`, comprueba si l'entornu virtual está activu u si la carpetina de `pipx` está en `$PATH`.

## Conetal la cuenta

Arranca l'asistente interactivu d'entrada:

```sh
omi auth login
```

Pués escohel dentrar col navegaol u pegal una llave API de desenrollador Omi. La entrada interactiva escuendi la llave; ten curiáu i nu la dehis nel estorial del terminal.

Pa dentrar diretamente col navegaol:

```sh
omi auth login --browser
```

Dentra nel mesmu ordinaol en el que corra el terminal: la resposta d'autorización va a una direción local. Sigue las instrucionis de la pantalla.

Agora comprueba la configuración i la llave API:

```sh
omi auth status
omi auth whoami
```

`status` muestra l'estau local i escuendi los secretus, pero nu comprueba col servidor. `whoami` haz una petición autorizada; si va bien, confirma que las tus credencialis huncionan, pero nu muestra el tu nombri.

La configuración está en `~/.omi/config.toml`. Nu compartas esti ficheru: pué contener secretus d'entrada.

## Esplorandu los datus

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista vacía pué significar namás que nu hai datus que correspondan. Pa deprendel los filtros de cada mandau, mira l'ayuda:

```sh
omi memory list --help
omi action-item list --help
```

## Salida JSON i paginación

Pon la opción global `--json` **enantis** del grupu de mandaus:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primer mandau pidi los primerus 25 recuerdus; el segundu pidi los siguientis 25. Una página nu sueli estal completa. La salida JSON guarda tolos identificadoris, mientris que las tablas de la pantalla los acortan.

Pa escrebil una página nun ficheru:

```sh
omi --json memory list --limit 25 --offset 0 > recuerdus-página-1.json
```

La redireción cria u sobrescrebi un ficheru local. Comprueba que'l mandau hya funcionau enantis d'usar el conteniu. Los erroris van a stderr; un ficheru vacíu nu quier dicir que nu haya datus. Los ficherus esportaus puen contener secretus: guardalos de forma segura.

## Salir

```sh
omi auth logout
```

Esti mandau quita las credencialis guardás localmenti. Pa revocal la llave nel servidor, usa la hestión de llaves de desenrollador ena tuya cuenta.

Pa más mandaus i opcionis avanzás, mira la [guía principal n'inglés](../README.md) i `omi --help`.
