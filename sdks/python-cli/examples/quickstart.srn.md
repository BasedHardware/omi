# Fosi stap nanga omi-cli

Disi gidsi e fruklari den fosi komando fu omi-cli na ini Sranantongo. Den nen fu den komando nanga den boskopu fu a programa e tan na ini Ingrisi. Den eksempre na ini a gidsi disi no e kenki den memori, den taki, den aksi-item, noso den gol fu yu.

## Instal

Yu abi fanowdu: Python 3.10 noso moro nyun, nanga wan Omi account.

Efu `pipx` de:

```sh
pipx install omi-cli
omi --help
```

Na wan tra fasi, yu kan instal en na ini wan aktif Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Efu a terminal no kan feni `omi`, dan luku efu a virtual environment de aktief, noso efu a pipx folder de na ini `$PATH`.

## Konekti yu account

Bigin a interactief login wizard:

```sh
omi auth login
```

Yu kan kisi fu login nanga wan browser, noso fu plak wan Omi developer API key. A interactief login e kibri yu key; no libi en na ini a terminal history.

Fu login direkt nanga browser:

```sh
omi auth login --browser
```

Login na tapu a srefi komputer pe a terminal e wroko: a antwort fu autorisatie e gebroiki wan lokale adres. Fou den instruktie na tapu a skerm.

Dan, luku a konfiguratie nanga a API key:

```sh
omi auth status
omi auth whoami
```

`status` e sori a lokale situatie èn e kibri sekret, ma a no e kontroleer e validiteit na tapu a server. `whoami` e meki wan request nanga autorisatie; efu a wroko bun, dan a e sori taki yu kredensial e wroko, sondro fu sori yu nen.

A konfiguratie e tan na ini `~/.omi/config.toml`. No prati a file disi: kande sekret fu login de na ini.

## Luku data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Wan lege lijst kan betekeni gewoon taki no data de di e miti a query. Fu leri den filter fu ibri komando, luku na a help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON output nanga pagina

Poti a global `--json` optie **bifo** a komando-grupu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

A fosi komando e aksi fu den fosi 25 memori; a di fu tu e aksi fu den 25 di e kon na baka. Wan pagina no de wan heri backup. JSON output e hori ala identificatie, ma den tafel na tapu skerm kan syfer den pikinso fu kan luku.

Fu kibri wan pagina na ini wan file:

```sh
omi --json memory list --limit 25 --offset 0 > memori-pagina-1.json
```

A redirekti disi e meki noso e skrifi abra wan lokale file. Bifo yu gebroiki a konten, luku taki a komando ben e kaba nanga bun. Den fowtu e go na stderr; wan lege file no e gi garantia taki no data de. Den export file kan abi persoonlijke data: kibri den.

## Logout

```sh
omi auth logout
```

A komando disi e figi den kredensial di kibri na ini yu komputer. Fu trowe a key na tapu a server, gebroiki a developer-key beheer na ini yu account.

Fu tra komando nanga moro opsein, luku [a Ingrisi hoofdgids](../README.md) nanga `omi --help`.
