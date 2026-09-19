# Començar amb omi-cli

Aquesta guida mòstra las primièras comandas en occitan. Los noms de las comandas e los messatges del sistèma demòran en anglés. Los exemples de lectura donats aicí modificaràn pas vòstras memòrias, conversacions, listas d'accions o tòcas.

## Installar lo programa

Requeriments: Python 3.10 o una version mai recenta e un compte Omi.

> Atencion: Lo nom del paquet sus PyPI es **`omi-cli`**, mentre que la comanda qu'es executada aprèp l'installacion es **`omi`**. Existís un autre paquet sens relacion sonat `omi` sus PyPI — installetz pas aquel paquet.

Se `pipx` es installat:

```sh
pipx install omi-cli
omi --help
```

Coma alternativa, dins un environament virtual Python actiu:

```sh
python -m pip install omi-cli
omi --help
```

Se lo terminal tròba pas `omi`, verificatz que l'environament virtual siá actiu o que lo repertòri de `pipx` siá dins vòstre `PATH`.

## Connectar vòstre compte

Aviar l'assistent interactiu:

```sh
omi auth login
```

Causissètz de vos connectar pel navigador, o causissètz l'opcion per pegar una clau API de desvolopaire Omi. L'entrada interactiva rescond la clau; picatz pas la clau dins de comandas que demòran dins l'istoric del terminal.

Per una connexion dirècta pel navigador:

```sh
omi auth login --browser
```

Completatz la connexion sus lo meteis ordenador ont lo terminal s'executa, perque l'autentificacion tòrna a una adreça locala. Seguissètz las instruccions sus l'ecran.

Aprèp aquò, verificatz la configuracion e l'accès a l'API:

```sh
omi auth status
omi auth whoami
```

`status` mòstra l'estat local e rescond los secrets, mas los verifica pas amb lo servidor. `whoami` manda una requèsta autentificada; la capitada significa que vòstres identificants foncionan corrèctament.

La configuracion es enregistrada per defaut dins `~/.omi/config.toml`. Partejatz pas aqueste fichièr perque conten vòstres identificants privats.

## Veire vòstras donadas

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista voida pòt simplament significar que i a pas d'elements que correspondon a la requèsta. Per comprene los filtres d'una comanda, consultatz l'ajuda:

```sh
omi memory list --help
omi action-item list --help
```

## Obténer de JSON e navigar per las paginas

Plaçatz l'opcion globala `--json` **abans** lo grop de comandas:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

La primièra comanda demanda los 25 primièrs enregistraments; la segonda demanda los 25 seguents. Per aquò, una pagina es pas una còpia de seguretat completa. Lo resultat JSON consèrva los identificadors complets, mentre que las taulas los pòdon acorchir.

Per enregistrar una pagina dins un fichièr:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pagina-1.json
```

Aquesta redireccion crèa o remplaça un fichièr local. Abans d'utilizar lo contengut, asseguratz-vos que la comanda a capitat. Las errors son escrichas sus stderr; un fichièr void es pas una pròva que i a pas de donadas. Gardatz aqueste fichièr en seguretat perque pòt conténer d'informacions personalas.

## Desconnectar (Log out)

```sh
omi auth logout
```

Aquesta comanda suprimís los identificants enregistrats localament. Per revocar una clau sul servidor, utilizatz la gestion de las claus de desvolopaire dins vòstre compte.

Per d'autras comandas e d'opcions avançadas, consultatz la guida principala en anglés:
[../README.md](../README.md) e `omi --help`.
