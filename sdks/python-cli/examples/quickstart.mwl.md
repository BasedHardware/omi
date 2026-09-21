# Purmeiros passos cun omi-cli

Esta guia mustra ls purmeiros passos cun omi-cli, scrita an mirandés. Los nomes de ls comandos i las mensaiges de l porgrama quedan an anglés. Los eisemplos d'esta guia nun altéran las tuas mimórias, cumbersas, eilemientos d'açon ni oubjetibos.

## Anstalaçon

Percisas de Python 3.10 ó superior, i ua cuonta Omi.

Si `pipx` yá stá:

```sh
pipx install omi-cli
omi --help
```

Ó, puodes anstalá-lo drento dun ambiente birtual de Python atibo:

```sh
python -m pip install omi-cli
omi --help
```

Si l terminal nun ancontra `omi`, berifica si l ambiente birtual stá atibo ó si la pasta de `pipx` stá ne l `$PATH`.

## Lhigar la tua cuonta

Ampeça l assistente de antrada anteratibo:

```sh
omi auth login
```

Puodes scoler: antra cun l nabegador ó cola ua chabe API de zambolbedor Omi. La antrada anteratiba scunde la chabe; pon antençon i nun la deixes na stória de l terminal.

Pa antra diretamente cun l nabegador:

```sh
omi auth login --browser
```

Antra na mesma máquina adonde stá l terminal: la repuosta de outorizaçon usa un zhitio local. Segue las anstruçones ne l ecran.

Agora berifica la cunfiguraçon i la chabe API:

```sh
omi auth status
omi auth whoami
```

`status` mustra l stado local i scunde ls segredos, mas nun berifica cun l serbidor. `whoami` ambia ua petiçon outorizada; se correr bien, sclarece que las tuas credenciales funcionan, mas nun amostra l teu nome.

La cunfiguraçon stá an `~/.omi/config.toml`. Nun cumpartas este ficeiro: puode tener segredos de antrada.

## Splorando ls dados

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ua lista bázia puode simplesmente quier dezir que nun eisisten dados que correspundan. Para daprender ls filtros de cada comando, buolta a la ajuda:

```sh
omi memory list --help
omi action-item list --help
```

## Salida JSON i paiginizaçon

Pone la ouçon global `--json` **antes** de l grupo de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

L purmeiro comando pega ls purmeiros 25 registros; l segundo pega ls 25 seguintes. Ua páigina nun ye siempre cumpleta. La salida JSON guarda todos ls eidantificadores, anquanto las tabelas ne l ecran ls acurtan.

Para scriver ua páigina nun ficeiro:

```sh
omi --json memory list --limit 25 --offset 0 > registros-páigina-1.json
```

La redireçon cria ó subrescribe un ficeiro local. Berifica que l comando funcionou antes d'usar l cuntenido. Las falhas ban pa stderr; un ficeiro bazio nun quier dezir que nun hai dados. Los ficeiros sportados puoden tener segredos: guardalhes cun sigurança.

## Salir

```sh
omi auth logout
```

Este comando saca las credenciales guardadas localmente. Para rebocar la chabe ne l serbidor, usa la admenistraçon de chabes de zambolbedor de la tua cuonta.

Para mais comandos i ouçones abançadas, buolta a la [guia percipal an anglés](../README.md) i `omi --help`.
