# Los primièrs passes amb omi-cli

Aquesta guida explica las primièras comandas (commands) d'omi-cli en occitan. Los noms de las comandas e los messatges del programa demòran en anglés. Los exemples de recèrca mostrats aicí cambián pas vòstras memòrias (memories), vòstras conversacions (conversations), vòstras accions (action items) ni vòstres objectius (goals).

## Installacion

Cal: Python 3.10 o mai recent, e un compte Omi.

Se avètz `pipx`:

```sh
pipx install omi-cli
omi --help
```

Podètz tanben l'installar dins un environament virtual Python actiu:

```sh
python -m pip install omi-cli
omi --help
```

Se lo terminal tròba pas `omi`, asseguratz-vos que l'environament virtual es actiu o que lo dorsièr de `pipx` es dins `$PATH`.

## Connectar vòstre compte

Aviatz l'assistent interactiu:

```sh
omi auth login
```

Causissètz la connexion pel navigador o lo pegatge d'una clau API de desvolopaire Omi. L'entrada interactiva amaga la clau; evitatz d'escriure-la dins una comanda que demorariá dins l'istoric del terminal.

Per anar dirèctament al navigador:

```sh
omi auth login --browser
```

Connectatz-vos sul meteis ordinator que lo terminal: la responsa d'autenticacion vai a l'adreça locala. Seguètz las instruccions sus l'ecran.

Puèi, verificatz la configuracion e l'accès API:

```sh
omi auth status
omi auth whoami
```

`status` mòstra l'estat local e amaga lo secret, mas verifica pas la validitat sul servidor. `whoami` fa una demanda autenticada; se capitèt, es clar que las credencialas foncionan, sens mostrar vòstre nom.

La configuracion es salvada per defaut dins `~/.omi/config.toml`. Partegetz pas aqueste fichièr: pò conténer de credencialas privadas.

## Explorar vòstras donadas

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista voida significa sovent pas que res correspond pas a la recèrca. Utilizatz l'ajuda per trobar los filtres de cada comanda:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e paginacion

Metètz l'opcion globala `--json` **abans** lo grop de comandas:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

La primièra comanda demanda las primièras 25 memòrias; la segonda las 25 seguentas. Una pagina sola es pas una còpia completa. La sortida JSON preserva los nombres entièrs, mentre que las taulas sus l'ecran los pòdon abreujar.

Per salvar una pagina dins un fichièr:

```sh
omi --json memory list --limit 25 --offset 0 > memòrias-pagina-1.json
```

Aquesta redireccion crèa o substituís un fichièr local. Asseguratz-vos que la comanda es acabada abans d'utilizar lo contengut. Las errors son escrichas dins la sortida d'error (stderr); un fichièr void es pas una pròva que i aja pas de donadas. Un fichièr exportat pò conténer d'informacions personalas: gardatz-lo privat.

## Desconectar

```sh
omi auth logout
```

Aquesta comanda escafa las credencialas salvadas localament. Per invalidar una clau sul servidor, utilizatz la gestion de las claus de desvolopaire dins vòstre compte.

Per mai de comandas e d'opcions, vejatz la [guida principala en anglés](../README.md) e `omi --help`.
