# Fosi stap nanga omi-cli

Disi gidsi e sori den fosi komando (commands) fu omi-cli na ini Sranantongo. Den nen fu den komando nanga den boskopu fu a program e tan na Ingrisi. Den eksempre fu suku di e sori dyaso no e kenki yu memori (memories), yu taki (conversations), yu wroko (action items) noso yu marki (goals).

## Instal

San yu mus abi: Python 3.10 noso moro nyun, nanga wan Omi akanti.

Efu yu abi `pipx`:

```sh
pipx install omi-cli
omi --help
```

Yu kan instal en tu na ini wan Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Efu a terminal no feni `omi`, meki seker taki a virtual environment e wroko noso taki a `pipx` folder de na ini `$PATH`.

## Konkti yu akanti

Bigin a asistenti:

```sh
omi auth login
```

Kies fu go na ini nanga a browser noso fu plaki wan Omi developer API kiy. A interaktif input e kibri a kiy; no skrifi a kiy na ini wan komando di o tan na ini a terminal historia.

Fu go direkt na ini a browser:

```sh
omi auth login --browser
```

Go na ini na a srefi komputer leki a terminal: a antworti fu autentikasi e go na a lokali adres. Folo den instruksi na tapu a skerm.

Baka dati, kontrole a konfigurasi nanga API akses:

```sh
omi auth status
omi auth whoami
```

`status` e sori a lokali situwasi nanga e kibri a sekret, ma a no e kontrole efu a bun na tapu a server. `whoami` e meki wan autentikasi fersi; efu a wroko, dan a krin taki den kredensial e wroko, sondro fu sori yu nen.

A konfigurasi e tan na ini `~/.omi/config.toml`. No prati disi file: a kan abi privat kredensial.

## Luku yu data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Wan lege listi e beteki fu no abi sani di e miti a suku. Gebruik a yepi fu feni den filter fu ibri komando:

```sh
omi memory list --help
omi action-item list --help
```

## JSON nanga papa

Poti a global opsen `--json` **fosi** a komando grupu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

A fosi komando e aksi den fosi 25 memori; a di fu tu e aksi den 25 di e kon baka. Wan papa no de wan full kopia. JSON e kibri den heel nomru, ma den tafra na tapu a skerm kan syatu den.

Fu kibri wan papa na ini wan file:

```sh
omi --json memory list --limit 25 --offset 0 > memori-papa-1.json
```

Disi redireksi e meki noso e skrifi abra wan lokali file. Meki seker taki a komando kla fosi yu gebroik a kontenti. Den fowtu e skrifi go na a fowtu output (stderr); wan lege file no de wan pruf taki no abi data. Wan eksport file kan abi persun birifrow: kibri en privat.

## Komoto

```sh
omi auth logout
```

Disi komando e figi den kredensial di e kibri na ini a lokali. Fu meki wan kiy no wroko moro na tapu a server, gebroik a developer kiy management na ini yu eigi akanti.

Fu moro komando nanga opsen, luku a [bigi gidsi na Ingrisi](../README.md) nanga `omi --help`.
