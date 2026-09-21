# Protili pasi cu omi-cli

Aestu ghid aratã protili comanduri di omi-cli tu armãneashti. Numile di comanduri shi mesagile di program rãmãn tu englezeshti. Exemplele di tu aestu ghid nu modificã amintirili, convorbirili, punctili di faptu icã scopurili a ta.

## Instalarea

Vã trebui Python 3.10 icã ma nou, shi un contu Omi.

Dacã `pipx` easti deja instalat:

```sh
pipx install omi-cli
omi --help
```

Alãntsã, lu poati instalã tu un mediu virtual Python activ:

```sh
python -m pip install omi-cli
omi --help
```

Dacã terminalu nu aflã `omi`, verificã dacã mediul virtual easti activ icã dacã cartela di `pipx` easti tu `$PATH`.

## Conectarea contului

Pleacã asistentul interactiv di intrare:

```sh
omi auth login
```

Poati s-alegã intrarea cu browserlu icã s-lipeascã unã clje API di dezvoltator Omi. Intrarea interactivã ascunde cljea; bagã di seami s-nu u lasi tu istoria di terminalu.

Pentru intrare directã cu browserlu:

```sh
omi auth login --browser
```

Intrã di la aceași mașinã iu lucreadzã terminalu: rãspunsu di autorizare s-ducã la unã adresã localã. Urmeadzã instructsile di pi ecran.

Acum verificã cunfigurarea shi cljea API:

```sh
omi auth status
omi auth whoami
```

`status` aratã starea localã shi ascunde secreturile, ma nu verificã cu serverlu. `whoami` fa unã cerere autorizatã; dacã reusesc, confirmã cã credentialele a ta lucreadzã, ma nu aratã numele a ta.

Cunfigurarea easti tu `~/.omi/config.toml`. Nu sparti aestu document: el poati s-aibã secreturi di intrare.

## Discuprind datele

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Unã listã goalã poati s-însemne cã nu easti date cari s-potriveascã. Pentru a nvitsã filturile di hondro comandu, vedzi agiutorlu:

```sh
omi memory list --help
omi action-item list --help
```

## Ieșirea JSON shi paghinarea

Puni optsia globalã `--json` **nãinti** di grupa di comanduri:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prota comandã aduc protile 25 amintiri; a doua aduc amintirile di ma nãntru. Unã paghinã nu easti adesea plinã. Ieșirea JSON tsãni tuti identificatorili, ma tabelele di pi ecran li scurtã adesea.

Pentru a scrii unã paghinã tu un document:

```sh
omi --json memory list --limit 25 --offset 0 > amintiri-paghinã-1.json
```

Rediretsionarea creeadzã icã ascre un document local. Verificã cã comanda reusi nãinti di a adhiljitã conținutlu. Erorile merg la stderr; un document gol nu s-însemne cã nu easti date. Documentele exportate pot s-aibã secreturi privati: tsãni-le sigur.

## Ieșirea din cont

```sh
omi auth logout
```

Aestã comandã scoate credentialele tsãnute local. Pentru a anulã cljea pi serverlu, folosii administrarea di cljei di dezvoltator tu contu a ta.

Pentru ma multi comanduri shi optsii avansati, vedzi [ghidul principal tu englezeshti](../README.md) shi `omi --help`.
