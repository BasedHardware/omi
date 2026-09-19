# Prinsepet pot omi-cli

Iñengulo este na giniha para i fine'nana na tinago' gi fino' Chamorro. I na'an
tinago' yan infotmasion programa ma'pos gi fino' Engles. Este siha na ihemplo ti para
u tulaika i hinasso-mu, kuentos, che'cho' pat tinane'.

## Plantan i Programa

Nesisen: Python 3.10 pat mas nuebu yan un kuenta Omi.

Kao guaha `pipx` gi masen-mu:

```sh
pipx install omi-cli
omi --help
```

Siña lokkue' un planta gi un dibision Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Kao ti ha li'e' i terminal `omi`, chék kuttan pot `$PATH` pat `pipx`.

## Konne' i Kuentan-mu

Tutuhon i ayuda interaktibu:

```sh
omi auth login
```

Ayek humalom gi browser pat pega i Omi API key.
Este na modu ha na'atuk i key; chamo tútuge' gi tinago' para ti u saga gi historiyan terminal.

Para un hanao direkto gi browser:

```sh
omi auth login --browser
```

Humalom gi mismu komputadora nai gaige i terminal. Tatiyi i instruksion gi pantaya.

Despues, chék i areklo yan aseso para API:

```sh
omi auth status
omi auth whoami
```

`status` ha na'annok i areklon lokat yan ha atuk i sekreto. `whoami` ha prueba na manggai balidasion i key.

To'du areklo gaige gi `~/.omi/config.toml`. Chamo fáfana' este na dokumento sa' guaha sekreto.

## Eskoba i Notan-mu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Kao taigue notan-mu, put fabot usa i ayuda:

```sh
omi memory list --help
omi action-item list --help
```

## Na'halom JSON yan Pahiña (Pagination)

Pega i globåt `--json` **antes** di i tinago':

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fine'nana na tinago' ha rikuesta 25 na hinasso; segundo ha rikuesta i 25 mamaila'. JSON ha na'fitme to'du ID.

Para un satba un pahiña gi dokumento:

```sh
omi --json memory list --limit 25 --offset 0 > hinasso-pahina-1.json
```

Este na dokumento siña guaha pribådu na infotmasion: adahi yan prutehi.

## Hanao Huyong (Logout)

```sh
omi auth logout
```

Este na tinago' ha na'suha i key gi komputadora. Para un na'suha i key gi server, usa i developer key portal gi kuentan-mu.

Para mas tinago', atan i [guha gi fino' Engles](../README.md) yan `omi --help`.
