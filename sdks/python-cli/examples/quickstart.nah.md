# Achtopa Ipan omi-cli

Inin tlahcuilolli quitomawa achtopa tlanawatilli ika nahuatlahtolli. Tlanawatilli
intokaywan wan tlahtolpamitl mocawaseh ika ingleslahtolli. Inin tlatlanilistli
axquitepapatlas momemoriawan, mononotzaliswan, motequitiyo, noso motlamanilistli.

## Quitlalilis Programah

Tlen polihui: Python 3.10 noso yancuic wan se Omi cuenta.

Tla ticpiya `pipx`:

```sh
pipx install omi-cli
omi --help
```

Noihqui hueli tictequiltis ipan se Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

## Ticsalolos Mocuenta

Tictemiltis login tepalewili:

```sh
omi auth login
```

Ticpehpenas ticalaquiz ika browser noso ika Omi API key.

Directo para browser:

```sh
omi auth login --browser
```

Zancualcan, tiquitaz tla yoli API:

```sh
omi auth status
omi auth whoami
```

Mocawa ipan `~/.omi/config.toml`. Ahmo xicmaca acah.

## Xiquitta Motlahtol

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## JSON wan amatlapal

Xictlali `--json` achtopa:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Xiquima ipan se amatl:

```sh
omi --json memory list --limit 25 --offset 0 > amatlapal-1.json
```

## Tiquisas (Logout)

```sh
omi auth logout
```

Xiquitta [Ingles tlahcuilolli](../README.md).
