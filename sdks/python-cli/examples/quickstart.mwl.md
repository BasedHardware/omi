# Purmeiros passos cun omi-cli

Esta guia splica ls purmeiros comandos (commands) de omi-cli an mirandés. Ls nomes de ls comandos i las mensaiges de l porgrama quedan an anglés. Ls eisemplos de busca amostrados eiqui nun altéran las tuas memórias (memories), las tuas cumbersas (conversations), las tuas tarefas (action items) nin ls teus oubjetibos (goals).

## Anstalaçon

Perciso: Python 3.10 ó mais nuobo, i ua cuenta Omi.

Se tenes `pipx`:

```sh
pipx install omi-cli
omi --help
```

Puedes tamien anstalar nun ambiente virtual de Python atibo:

```sh
python -m pip install omi-cli
omi --help
```

Se l terminal nun ancuntra `omi`, certifica-te de que l ambiente virtual stá atibo ó de que la pasta de `pipx` stá ne l `$PATH`.

## Lhigar la tue cuenta

Cumeça l'assistente anteratibo:

```sh
omi auth login
```

Scolhe antre pul nabegador ó pegar ua chabe API de zambolbedor Omi. L'amporta anteratibo scunde la chabe; eibita screbilha nua comando que quede ne l stórico de l terminal.

Para ir diretamente al nabegador:

```sh
omi auth login --browser
```

Antra ne l mesmo cumputador de l terminal: la repuosta d'outenticaçon bai pa l'endereço local. Sigue las anstruçones na telha.

Depuis, berifica la cunfiguraçon i l'acesso API:

```sh
omi auth status
omi auth whoami
```

`status` amostra l stado local i scunde l segredo, mas nun berifica la balidade ne l serbidor. `whoami` fa ua petiçon outenticada; se funcionar, stá claro que las credenciales funcionan, sin amostrar l teu nome.

La cunfiguraçon ye guardada por defunto an `~/.omi/config.toml`. Nun cumpartilhes este fexicheiro: puode tener credenciales priuadas.

## Splorar ls teus dados

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ua lista bazie normalmente solo quier dezir que nada correspunde a la busca. Usa l'ajuda para ancuntrar ls filtros de cada comando:

```sh
omi memory list --help
omi action-item list --help
```

## JSON i páiginas

Pone la oupçon global `--json` **antes** de l grupo de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

L purmeiro comando pede las purmeiras 25 memórias; l segundo las 25 seguintes. Ua páigina sola nun ye ua cópia cumpleta. La salida JSON cunserba ls númaros anteiros, mentres las tabelas na telha ls puoden acurtar.

Para guardar ua páigina nun fexicheiro:

```sh
omi --json memory list --limit 25 --offset 0 > memórias-páigina-1.json
```

Esta redireçon creia ó subrescribe un fexicheiro local. Certifica-te de que l comando acabou antes d'usar l cuntenido. Las falhas son scritas na salida d'erro (stderr); un fexicheiro bazio nun ye ua proba de que nun hai dados. Un fexicheiro sportado puode tener anformaçon pessonal: guarda-lo priuado.

## Salir

```sh
omi auth logout
```

Este comando apaga las credenciales guardadas localmente. Para ambalidar ua chabe ne l serbidor, usa la geston de chabes de zambolbedor na tue própia cuenta.

Para mais comandos i oupçones, bê la [guia percipal an anglés](../README.md) i `omi --help`.
