# Guaha gi Tutuhon omi-cli

Este na giha ha eksplilika i primet na chinachalani gi fino' Chamoru. I na'an
tinago' siha yan mensahe ginen i programa para u fansaga gi fino' Ingles.

## Na'setbisi i Programa

Nisisita: Python 3.10 pat nuebu yan kuenta Omi.

Kao guaha `pipx`:

```sh
pipx install omi-cli
omi --help
```

Pat gi virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

## Fanhalom gi Kuentamu

Tutuhon i login:

```sh
omi auth login
```

Direkto gi browser:

```sh
omi auth login --browser
```

Egsemina i API:

```sh
omi auth status
omi auth whoami
```

Magahet gi `~/.omi/config.toml`. Munga mana'share.

## Li'e i Data siha

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## Fanayek JSON yan Pahina

Po'lo `--json` gi mo'na:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Satba un pahina:

```sh
omi --json memory list --limit 25 --offset 0 > hinasso-pahina-1.json
```

## Hanao Huyong (Logout)

```sh
omi auth logout
```

Atan [Giha gi Fino' Ingles](../README.md).
