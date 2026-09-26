# Primers passos amb omi-cli

Aquesta guia explica les primeres ordres en català. Els noms de les ordres i
els missatges del programa es mantenen en anglès. Els exemples de consulta que
apareixen aquí no modifiquen els vostres records, converses, tasques ni objectius.

## Instal·lar el programa

Requisits: Python 3.10 o una versió posterior i un compte d'Omi.

Si teniu `pipx` instal·lat:

```sh
pipx install omi-cli
omi --help
```

Com a alternativa, podeu instal·lar-lo dins d'un entorn virtual de Python
activat:

```sh
python -m pip install omi-cli
omi --help
```

Si el terminal no troba `omi`, comproveu que l'entorn virtual estigui activat o
que el directori on `pipx` instal·la els seus executables estigui al vostre `PATH`.

## Connectar el vostre compte

Inicieu l'assistent interactiu:

```sh
omi auth login
```

Trieu iniciar sessió al navegador o l'opció d'enganxar una clau API de
desenvolupador d'Omi. L'entrada interactiva oculta la clau; eviteu escriure-la
en una ordre que quedi a l'historial del terminal.

Per anar directament al navegador:

```sh
omi auth login --browser
```

Inicieu sessió al mateix ordinador que el terminal: la resposta d'autenticació
utilitza una adreça local (localhost). Seguiu les instruccions que apareixen en
pantalla.

Després, verifiqueu la configuració i l'accés a l'API:

```sh
omi auth status
omi auth whoami
```

`status` mostra l'estat local i oculta el secret, però no comprova la seva
validesa al servidor. `whoami` realitza una sol·licitud autenticada; si té
èxit, confirma que les credencials funcionen, sense mostrar necessàriament el
vostre nom.

La configuració es desa a `~/.omi/config.toml` per defecte. No compartiu aquest
fitxer: pot contenir les vostres credencials.

## Consultar les vostres dades

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una llista buida pot significar simplement que no hi ha elements que coincideixin
amb la consulta. Utilitzeu l'ajuda per descobrir els filtres de cada ordre:

```sh
omi memory list --help
omi conversation list --help
omi action-item list --help
```

## Obtenir JSON i navegar per les pàgines

Col·loqueu l'opció global `--json` **abans** del grup d'ordres:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

La primera ordre demana els primers 25 records; la segona, els 25 següents. Una
sola pàgina no és, per tant, una còpia de seguretat completa. La sortida JSON
conserva els identificadors complets, mentre que les taules poden escurçar-los
per mostrar-los.

Per desar una pàgina en un fitxer:

```sh
omi --json memory list --limit 25 --offset 0 > records-pagina-1.json
```

Aquesta redirecció crea o reemplaça el fitxer local. Comproveu que l'ordre ha
finalitzat correctament abans d'utilitzar el seu contingut. Els errors s'escriuen
a la sortida d'error estàndard (stderr); un fitxer buit no garanteix que no hi
hagi dades. El fitxer exportat pot contenir informació personal: manteniu-lo privat.

## Tancar la sessió

```sh
omi auth logout
```

Aquesta ordre elimina les credencials desades localment. Per revocar una clau al
servidor, utilitzeu la gestió de claus de desenvolupador del vostre compte.

Per a la resta d'ordres i opcions avançades, consulteu la
[guia principal en anglès](../README.md), `omi --help` i la comunitat a [discord.omi.me](https://discord.omi.me).
