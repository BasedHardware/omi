# Luyantiku ya omi-cli (Kikongo)

Mukanda yai ke tendula bantuma ya ntete na Kikongo.

## Kutula Pulogalamu

Yo ke lomba: Python 3.10 mpe konte ya Omi.

```sh
pipx install omi-cli
omi --help
```

## Kukota na Konte

```sh
omi auth login
omi auth login --browser
omi auth status
omi auth whoami
```

Bomba na `~/.omi/config.toml`.

## Kutala Bansangu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## Kubaka JSON

```sh
omi --json memory list --limit 25 --offset 0 > bansangu-1.json
```

## Kubasika (Logout)

```sh
omi auth logout
```

Tala [Mukanda ya Kingelesi](../README.md).
