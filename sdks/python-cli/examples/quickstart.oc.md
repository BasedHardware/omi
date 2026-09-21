# Primièrs passes amb omi-cli

Aquesta guida presenta los primièrs comandaments d'omi-cli en occitan. Los noms dels comandaments e los messatges del programa demòran en anglés. Los exemples d'aquesta guida modifiquèssen pas vòstras remembranças, conversacions, accions o objectius.

## Installacion

Avètz besonh de Python 3.10 o mai recent, e d'un compte Omi.

Se `pipx` es ja installat:

```sh
pipx install omi-cli
omi --help
```

Autrament, installatz-lo dins un environament virtual Python actiu:

```sh
python -m pip install omi-cli
omi --help
```

Se lo terminal tròba pas `omi`, verificatz se l'environament virtual es actiu o se lo repertòri de pipx es dins `$PATH`.

## Connectar vòstre compte

Lancetz l'assistent de connexion interactiu:

```sh
omi auth login
```

Podètz causir de vos connectar amb lo navigador o de pegar una clau API de desvelopaire Omi. La connexion interactiva amaga vòstra clau; siatz prudent e daissatz-la pas dins l'istoric de vòstre terminal.

Per vos connectar dirèctament amb lo navigador:

```sh
omi auth login --browser
```

Connectatz-vos sul meteis ordinator ont lo terminal fonciona: la responsa d'autorizacion utiliza una adreça locala. Seguètz las instruccions a l'ecran.

Verificatz ara la configuracion e la clau API:

```sh
omi auth status
omi auth whoami
```

`status` mòstra l'estat local e amaga los secrets, mas verifica pas amb lo servidor. `whoami` fa una requèsta autorizada; se capita, confirma que vòstra autorizacion fonciona, mas mòstra pas vòstre nom.

La configuracion se tròba dins `~/.omi/config.toml`. Partejatz pas aqueste fichièr: pòt conténer de secrets de connexion.

## Explorar las donadas

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista voida pòt simplament significar qu'i a pas de donadas que correspondon a la requèsta. Per aprendre los filtres de cada comandament, consultatz l'ajuda:

```sh
omi memory list --help
omi action-item list --help
```

## Sortida JSON e paginacion

Metètz l'opcion globala `--json` **abans** lo grop de comandaments:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lo primièr comandament recupera las primièras 25 remembranças; lo segond recupera las 25 seguentas. Una pagina es sovent pas plena. La sortida JSON conserva totes los identificadors, mentre que las taulas a l'ecran los truncàn sovent.

Per escriure una pagina dins un fichièr:

```sh
omi --json memory list --limit 25 --offset 0 > remembranças-pagina-1.json
```

La redireccion crea o escriu sus un fichièr local. Verificatz que lo comandament a reüssit abans d'utilizar lo contengut. Las errors van a stderr; un fichièr void significa pas qu'i a pas de donadas. Los fichièrs exportats pòdon conténer d'informacion privada: gardatz-los en seguretat.

## Desconnexion

```sh
omi auth logout
```

Aqueste comandament remòu l'autorizacion locala enregistrada. Per revocar la clau sul servidor, utilizatz la gestion de las claus de desvelopaire sus vòstre compte.

Per d'autres comandaments e d'opcions avançadas, vejatz la [Guida principala en anglés](../README.md) e `omi --help`.
