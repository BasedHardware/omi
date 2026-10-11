# Éischt Schrëtt mat omi-cli

Dëse Guide erkläert déi éischt Kommandoen (commands) vum omi-cli op Lëtzebuergesch. D'Nimm vun de Kommandoen an d'Noriichte vum Programm bleiwen op Englesch. D'Beispiller vum Sichen, déi hei gewise ginn, änneren Är Erënnerungen (memories), Är Gespréicher (conversations), Är Aktiounspunkten (action items) oder Är Ziler (goals) net.

## Installatioun

Noutwendeg: Python 3.10 oder méi nei, an en Omi-Kont.

Wann Dir `pipx` hutt:

```sh
pipx install omi-cli
omi --help
```

Dir kënnt et och an enger aktiver Python-Virtualumgebung installéieren:

```sh
python -m pip install omi-cli
omi --help
```

Wann den Terminal `omi` net fënnt, vergewëssert Iech, datt d'Virtualumgebung aktiv ass oder datt den `pipx`-Dossier am `$PATH` ass.

## Äre Kont verbannen

Start den interaktiven Assistent:

```sh
omi auth login
```

Wielt tëscht dem Login iwwer de Browser oder dem Asetzen vun engem Omi Developer API-Schlëssel. D'interaktiv Eingab verstoppt de Schlëssel; vermeit et, deen an engem Kommando ze schreiwen, deen an der Terminalgeschicht gespäichert gëtt.

Fir direkt op de Browser ze goen:

```sh
omi auth login --browser
```

Loggt Iech um selwechte Computer an wéi den Terminal: d'Authentifikatiounsäntwert geet op déi lokal Adress. Follegt den Uweisungen um Écran.

Duerno kënnt Dir d'Konfiguratioun an den API-Zougang iwwerpréiwen:

```sh
omi auth status
omi auth whoami
```

`status` weist den lokalen Zoustand a verstoppt de Secret, awer et iwwerpréift net d'Gëltegkeet um Server. `whoami` mécht eng authentifizéiert Ufro; wann déi geléngt, ass et kloer datt d'Zougangsdaten funktionéieren, ouni Ären Numm ze weisen.

D'Konfiguratioun gëtt standardméisseg an `~/.omi/config.toml` gespäichert. Deelt dës Datei net: si kann vertraulech Zougangsdaten enthalen.

## Är Daten entdecken

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Eng eidel Lëscht heescht meeschtens just, datt näischt mat der Sich iwwereneestëmmt. Benotzt d'Hëllef, fir d'Filtere vun all Kommando ze fannen:

```sh
omi memory list --help
omi action-item list --help
```

## JSON an Paginatioun

Setzt déi global Optioun `--json` **virun** d'Kommando-Grupp:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Den éischte Kommando freet déi éischt 25 Erënnerungen un; den zweete déi nächst 25. Eng Säit ass keng komplett Sécherung. D'JSON-Ausgab erhält déi ganz Zuelen, während d'Tabellen um Écran si kënnen ofkierzen.

Fir eng Säit an eng Datei ze späicheren:

```sh
omi --json memory list --limit 25 --offset 0 > erënnerungen-säit-1.json
```

Dës Ëmleedung erstellt oder iwwerschreift eng lokal Datei. Vergewëssert Iech, datt de Kommando fäerdeg ass, ier Dir den Inhalt benotzt. Feeler ginn op d'Feelerausgab (stderr) geschriwwen; eng eidel Datei ass kee Beweis, datt et keng Date gëtt. Eng exportéiert Datei kann perséinlech Informatioune enthalen: haalt si privat.

## Ausloggen

```sh
omi auth logout
```

Dëse Kommando läscht déi lokal gespäichert Zougangsdaten. Fir e Schlëssel um Server z'invalidéieren, benotzt d'Verwaltung vun den Developer-Schlësselen an Ärem eegene Kont.

Fir méi Kommandos an Optiounen, kuckt de [Haaptguide op Englesch](../README.md) an `omi --help`.
