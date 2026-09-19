# Ufänke mat omi-cli

Dëse Guide weist déi éischt puer Befehler op Lëtzebuergesch. D'Befehlsnimm an d'Systemmeldunge bleiwen op Englesch. D'Liesbeispiller, déi hei ugewise ginn, änneren Är Erënnerungen, Gespréicher, Aktiounslëschten oder Ziler net.

## De Programm installéieren

Ufuerderungen: Python 3.10 oder méi nei an en Omi-Konto.

> Opgepasst: De Package-Numm op PyPI ass **`omi-cli`**, wärend de Befehl, deen no der Installatioun leeft, **`omi`** ass. Et gëtt en anere Package ouni Bezuch mam Numm `omi` op PyPI — installéiert dëse Package net.

Wann `pipx` installéiert ass:

```sh
pipx install omi-cli
omi --help
```

Alternativ, an engem aktiven virtuelle Python-Environnement:

```sh
python -m pip install omi-cli
omi --help
```

Wann den Terminal `omi` net fënnt, kontrolléiert ob de virtuellen Environnement aktiv ass oder ob de `pipx`-Dossier an Ärem `PATH` steet.

## Äre Kont verbannen

Start den interaktiven Assistent:

```sh
omi auth login
```

Wielt de Login iwwer de Browser, oder wielt d'Optioun fir en Omi-Entwéckler-API-Schlëssel anzefügen. Den interaktiven Input verstoppt de Schlëssel; tippt de Schlëssel net a Befehler, déi an der Terminal-Historik bleiwen.

Fir en direkte Login iwwer de Browser:

```sh
omi auth login --browser
```

Maacht de Login op deem selwechte Computer wou den Terminal leeft, well d'Authentifikatioun op eng lokal Adress zréckkënnt. Follegt d'Instruktioune um Bildschierm.

Duerno kontrolléiert d'Konfiguratioun an den API-Zougang:

```sh
omi auth status
omi auth whoami
```

`status` weist de lokale Status a verstoppt Geheimnisser, kontrolléiert se awer net mam Server. `whoami` schéckt eng authentifizéiert Ufro; e Succès bedeit datt Är Umeldungsinformatioune richteg funktionéieren.

D'Konfiguratioun gëtt standardméisseg an `~/.omi/config.toml` gespäichert. Deelt dës Datei net, well se Är privat Umeldungsinformatioune enthält.

## Kuckt Är Donnéeën un

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Eng eidel Lëscht kann einfach bedeiten datt keng Elementer mat der Ufro iwwereneestëmmen. Fir d'Filtere vun engem Befehl ze verstoen, kuckt an d'Hëllef:

```sh
omi memory list --help
omi action-item list --help
```

## JSON kréien a Säite bliederen

Setzt déi global Optioun `--json` **virun** de Befehlsgrupp:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Den éischte Befehl freet déi éischt 25 Donnéeën un; deen zweeten déi nächst 25. Dofir ass eng Säit kee komplette Backup. Den JSON-Output behält déi komplett Identifikatiounen, wärend Tabellen se verkierze kënnen.

Fir eng Säit an enger Datei ze späicheren:

```sh
omi --json memory list --limit 25 --offset 0 > errennerungen-sait-1.json
```

Dës Ëmleedung erstellt oder ersetzt eng lokal Datei. Ier Dir den Inhalt benotzt, vergewëssert Iech datt de Befehl erfollegräich war. Feeler ginn op stderr geschriwwen; eng eidel Datei ass kee Beweis datt keng Donnéeë virleien. Déi exportéiert Datei ka perséinlech Informatiounen enthalen: haalt se sécher.

## Ausloggen (Log out)

```sh
omi auth logout
```

Dëse Befehl läscht déi lokal gespäichert Umeldungsinformatiounen. Fir e Schlëssel um Server ze widderhuelen, benotzt d'Entwéckler-Schlësselverwaltung an Ärem Kont.

Fir aner Befehler an erweidert Optiounen, kuckt w.e.g. an den Haaptguide op Englesch:
[../README.md](../README.md) an `omi --help`.
