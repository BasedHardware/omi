# Tacar co omi-cli

Sta guida la mostra i primi comandi in léngua vèneta. I nomi dei comandi e i messaji de sistema i resta in ingleze. I ezenpi de letura diti cuà no i modìfega mia le vostre memòrie, conversasion, liste de robe da fare o obietivi.

## Instalar el programa

Rechieziti: Python 3.10 o piasè novo e un conto Omi.

> Atension: El nome del pacheto so PyPI l'è **`omi-cli`**, mentre el comando che zira dopo l'instalasion l'è **`omi`**. Ghe ze n'altro pacheto sensa conetidùra ciamà `omi` so PyPI — no stà instalar chel pacheto là.

Se `pipx` l'è instalà:

```sh
pipx install omi-cli
omi --help
```

In alternativa, drento de un anbiente virtuałe Python ativà:

```sh
python -m pip install omi-cli
omi --help
```

Se el terminal no'l cata `omi`, verìfega che l'anbiente virtuałe el sìpia ativà o che la cartela de `pipx` la sìpia inte el to `PATH`.

## Ligare el to conto

Taca l'asistente interativo:

```sh
omi auth login
```

Seli de intrar tramite el navegadore web, o seli l'opsion par incolar na ciave API de zviłupatore Omi. L'inmesion interativa la sconde la ciave; no stà scrìvare la ciave in comandi che i pol restare inte ła cronolozìa del terminal.

Par intrar direto tramite el navegadore:

```sh
omi auth login --browser
```

Fa l'aceso so l'isteso conputer dove che zira el terminal, parché l'autenticasion la torna indrìo a un indirisso łocałe. Va drio a łe istrusion so el schermo.

Dopo de cuesto, verìfega la configurasion e l'aceso a łe API:

```sh
omi auth status
omi auth whoami
```

`status` el mostra el stato łocałe e el sconde i segreti, ma no'l verìfega col server. `whoami` el manda na dimanda autenticada; el suceso el vol dir che łe to credensiałi łe funsiona a dovere.

La configurasion la vien salvada de baze in `~/.omi/config.toml`. No stà spartire sto file cuà parché el ga drento łe to credensiałi privade.

## Vardare i to dati

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Na lista voda la pol vołer dir senplisemente che no ghe ze ełeminti che i corisponde a ła dimanda. Par conprendere i filtri de un comando, varda l'ajuto:

```sh
omi memory list --help
omi action-item list --help
```

## Ciapare JSON e zfojar łe pàjine

Meti l'opsion globałe `--json` **prima** del grupo de comandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

El primo comando el dimanda i primi 25 rezistri; el secondo el dimanda i 25 che vien dopo. Donca, na pàjina no ła ze na còpia de seguresa conpleta. L'èsito JSON el tien i identifegadori conpleti, mentre łe tabele łe pol scurtarli.

Par salvare na pàjina drento de un file:

```sh
omi --json memory list --limit 25 --offset 0 > memorie-pajina-1.json
```

Sto reindirìsamento el crea o el scanbia un file łocałe. Prima de doparare el contegnuo, verìfega che el comando el sìpia ndà a bon fin. I erori i vien scriti so stderr; un file vodo no'l ze mia na prova che no ghe sìpia dati. Tien sto file a el seguro parché el pol contegnere informasion personałi.

## Desconètarse (Log out)

```sh
omi auth logout
```

Sto comando el cava łe credensiałi salvade łocalmente. Par revocare na ciave so el server, dopara la zestion de łe ciavi de zviłupatore inte el to conto.

Par altri comandi e opsion vansade, varda par piazer la guida prinsipałe in ingleze:
[../README.md](../README.md) e `omi --help`.
