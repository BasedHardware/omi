# I finenna na pasu siha yan omi-cli

Para u tutuhon yan omi-cli, atan este na guia. I na'an i komandu siha yan i mensåhen i programa siha gaige gi fino' Ingles. I ehemplo siha gi este na guia ti mañulaika i hinasso-mu, i kuentos-mu, i cho'cho-mu, pat i planu-mu.

## Instalasion

Nesesita hao Python 3.10 pat mås, yan un kuenta Omi.

Yanggen gaige ha' i `pipx`:

```sh
pipx install omi-cli
omi --help
```

Pat siña un install gi un Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Yanggen ti ha sodda' i `omi` i terminal, atan yanggen i virtual environment macho'cho' pat yanggen i folder `pipx` gaige gi `$PATH`.

## Konekta i kuenta-mu

Tutuhon i interactive login wizard:

```sh
omi auth login
```

Siña un ayek: login gi browser pat paste un Omi developer API key. I interactive input ha na'håspok i key; e'ega' hao na ti u såga i key gi terminal history-mu.

Para un login direktu gi browser:

```sh
omi auth login --browser
```

Login gi hemta na komputadora, sa' i autorisasion ha usa un lokal na adires. Dedit i instruksion siha gi ekran.

Pues atan i setbisio yan i API key:

```sh
omi auth status
omi auth whoami
```

`status` ha na'ue hao i estådo lokal ya ha na'håspok i sekreto siha, lao ti ha atan i server. `whoami` ha chagi i kredensial gi server.

Gaige i setbisio gi `~/.omi/config.toml`. Ti un fa'nå'gue i file ni otro siha: siña gaige i sekreto siha.

## Atan i datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Yanggen tåya' datos gi list, siña ha' na ti guaha datos ni ma sodda'. Para un tungo' i komandu siha, atan i ayudo:

```sh
omi memory list --help
omi action-item list --help
```

## JSON yan i pahina siha

Po'lo i global option `--json` **åntes** di i komandu siha:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

I finenna na komandu ha chuli i finenna 25 na hinasso; i mina'dos ha chuli i otro 25. I un pahina ti kabålis. I JSON ha na'ue i identifier siha, lao i tabble gi ekran ha na'fanfion siha.

Para un tuge' i pahina gi file:

```sh
omi --json memory list --limit 25 --offset 0 > hinasso-pahina-1.json
```

I redirect ha fa'tinas un file lokal pat ha tuge' iya hulo'. Atan yanggen målai' i komandu åntes di un usa. Error siha lumà'là' gi stderr; i file ni tåya' content ti ha na'nu na tåya' datos. I file siha siña gaige i sekreto: na'fanmetgot siha.

## Fanhuyong

```sh
omi auth logout
```

I komandu ayo ha håsa i kredensial siha gi tano'. Para un kansela i key gi server, usa i developer key management gi kuenta-mu.

Para otro komandu siha yan opsion, atan i [English na guia](../README.md) yan `omi --help`.
