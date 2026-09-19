# Matangiriro ne omi-cli (Sena)

Buku ino iri kufokotoza mafambidwe akutoma mu Chisena. Madzina a mapulogalamu
anakhala mu Chingerezi.

## Kuikha Pulogalamu

Mukusoweka: Python 3.10 na akaunti ya Omi.

```sh
pipx install omi-cli
omi --help
```

## Kulumikiza Akaunti

```sh
omi auth login
omi auth login --browser
omi auth status
omi auth whoami
```

Sungani bwino pa `~/.omi/config.toml`.

## Kuona Mbiri Yanu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

## Kutenga JSON

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 0 > mbiri-1.json
```

## Kubuluka (Logout)

```sh
omi auth logout
```

Onani [Buku ya Chingerezi](../README.md).
