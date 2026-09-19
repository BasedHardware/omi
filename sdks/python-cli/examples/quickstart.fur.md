# Prims pas cun omi-cli

Cheste vuide e spieghe i prims comants cun omi-cli par furlan (Friulian). I nons dai comants e i messaçs dal program a son in inglês. I esemplis di consultazion mostrâts culì no cambiin lis tôs memoriis (memories), conversazions (conversations), azions di fâ (action items), o obietîfs (goals).

## Instalazion dal program

Rechisîts: Python 3.10 o plui resint e un account Omi.

Se tu âs instalât `pipx`:

```sh
pipx install omi-cli
omi --help
```

Al è pussibil instalâlu ancje intun ambient virtuâl Python:

```sh
python -m pip install omi-cli
omi --help
```

## Coneti il to account

Fâs partî l'assistent interatîf:

```sh
omi auth login
```

Sielç di jentrâ cul navigadôr o incolant la clâf API di svilupadôr Omi.

Par lâ drets tal navigadôr:

```sh
omi auth login --browser
```

Verifiche la configurazion e l'acès ae API:

```sh
omi auth status
omi auth whoami
```

`status` al mostre il stât locâl, intant che `whoami` al invie une richieste autenticade par confermâ la validitât des credenziâls tal servidôr.

## Esplore i tiei dâts

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Adopre l'aiût par discuvierzi i filtris par ogni comant:

```sh
omi memory list --help
omi action-item list --help
```

## Otignî JSON e pagjinazion

Met la opzion globâl `--json` **prime** dal grup di comants:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Par salvâ une pagjine intun file:

```sh
omi --json memory list --limit 25 --offset 0 > memoriis-pagjine-1.json
```

## Jessî dal account

```sh
omi auth logout
```

Chest comant al scancele lis credenziâls salvadis a nivel locâl.

Par altris comants e opzions, cjale la [vuide principâl in inglês](../README.md) e `omi --help`.
