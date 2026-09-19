# Cuminzari cu omi-cli

Sta guida ammustra li primi cumanna 'n sicilianu. Li noma dî cumanna e li missaggi di sistema arrèstanu 'n ngrisi. L'asempi di littura furnuti ccà nun càncianu li vostri ricordi, cunversazzioni, listi di cosi di fari o scopi.

## Nstallari lu prugramma

Requisiti: Python 3.10 o na virsioni cchiù ricenti e nu cuntu Omi.

> Attinzioni: Lu nomu dû pacchettu supra PyPI è **`omi-cli`**, mentri lu cumannu ca camina doppu la nstallazzioni è **`omi`**. C'è n'àutru pacchettu senza rilazzioni ca si chiama `omi` supra PyPI — nun nstallati ddu pacchettu.

Si `pipx` è nstallatu:

```sh
pipx install omi-cli
omi --help
```

N'alternativa, dintra n'ambienti virtuali Python attivu:

```sh
python -m pip install omi-cli
omi --help
```

Si lu terminali nun trova `omi`, assiguràtivi ca l'ambienti virtuali è attivu o ca la cartella di `pipx` s'attrova ntô vostru `PATH`.

## Culligari lu vostru cuntu

Accuminciati l'assistenti ntirattivu:

```sh
omi auth login
```

Scigghiti di tràsiri tramite lu navigaturi web, o scigghiti l'opzioni pi ncuddari na chiavi API di sviluppaturi Omi. L'input ntirattivu ammuccia la chiavi; nun scriviti la chiavi 'n cumanna ca ponnu arristari ntâ cronuluggìa dû terminali.

Pi tràsiri direttamenti tramiti lu navigaturi:

```sh
omi auth login --browser
```

Cumpritati l'accessu ntô stissu computer unni camina lu terminali, picchì l'autintificazzioni torna a n'indirizzu lucali. Sicutati li struzzioni supra lu schermu.

Doppu di chissu, virificati la cunfigurazzioni e l'accessu a l'API:

```sh
omi auth status
omi auth whoami
```

`status` ammustra lu statu lucali e ammuccia li segreti, ma nun li virìfica cû server. `whoami` manna na dumanna autintificata; lu successu signìfica ca li vostri cridinziali fùnzianu bonu.

La cunfigurazzioni veni sarvata pi difettu 'n `~/.omi/config.toml`. Nun spartiti stu file picchì cunteni li vostri dati pirsunali.

## Talìati li vostri dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista vacanti pò simpricimenti significari ca nun ci sunnu elementi ca currispùndinu â dumanna. Pi canùsciri li filtri d'un cumannu, talìati l'aiutu:

```sh
omi memory list --help
omi action-item list --help
```

## Uttèniri JSON e sfugghiari li pàggini

Miti l'opzioni glubbali `--json` **prima** dû gruppu di cumanna:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lu primu cumannu cerca li primi 25 riggistrazzioni; lu secunnu cerca li 25 succissivi. Dunque, na pàggina nun è na còpia di riserva cumpleta. Lu risurtatu JSON manteni l'identificatura cumpleti, mentri li tabbelli ponnu accurtàrili.

Pi sarvari na pàggina dintra nu file:

```sh
omi --json memory list --limit 25 --offset 0 > ricordi-paggina-1.json
```

Sta ridirezzioni crea o rimpiazza nu file lucali. Prima d'usari lu cuntinutu, assiguràtivi ca lu cumannu appi successu. L'erruri vèninu scritti supra stderr; nu file vacanti nun è na prova ca nun ci sunnu dati. Stu file pò cuntèniri dati pirsunali: sarvàtulu sicuru.

## Nèsciri (Log out)

```sh
omi auth logout
```

Stu cumannu leva li cridinziali sarvati lucalmenti. Pi rivucari na chiavi supra lu server, usati la gistioni dî chiavi sviluppaturi ntô vostru cuntu.

Pi àutri cumanna e opzioni avanzati, talìati la guida principali 'n ngrisi:
[../README.md](../README.md) e `omi --help`.
