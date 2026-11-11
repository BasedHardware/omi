# Initia cum omi-cli

Hic dux prima mandata Latine explicat. Mandatorum nomina et nuntii systematis Anglice manent. Exempla interrogationis hic allata tuas memorias, colloquia, pensa, neque proposita mutant.

## Programma instituere

Requisita: Python 3.10 vel recentior et ratio Omi.

Si `pipx` institutum habes:

```sh
pipx install omi-cli
omi --help
```

Vel intra activatum ambitum virtualem Pythonis:

```sh
python -m pip install omi-cli
omi --help
```

Si terminale `omi` non invenit, verifica ambitum virtualem activatum esse vel indicem executabilium `pipx` in tuo `PATH` contineri.

## Rationem tuam connectere

Priusquam data tua legere possis, `omi-cli` rationi tuae Omi iungendum est:

```sh
omi auth login
```

Mandatum navigatorium interretialem aperiet ad authenticationem perficiendam. Postquam feliciter connectitur, signum accessus tui in computatro servatur.

## Data tua consultare

Index memorias tuas:

```sh
omi memory list
```

Colloquia recentia perspicere:

```sh
omi conversation list
```

Ad auxilium generale de ullo mandato:

```sh
omi --help
```

## Exire

Cum sessionem finire vis, signum loci delere potes:

```sh
omi auth logout
```
