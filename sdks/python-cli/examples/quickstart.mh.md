# Jinoe ilo omi-cli

Pikinik in ej kwalok jet kien ko moktata ilo Kajin Majol. Etan kien ko im ennaan in jikin ko rej ped wot ilo Kajin Belle. Wanwon in riit ko rej letok ijin reban ukot am kememej, bwebwenato, laajrak in jerbal, ak kottobar ko.

## Kakwjarjar eok

Men ko rej aikuij: Python 3.10 ak emakaj lok im juon Omi account.

> Lale: Etan jikin eo ilo PyPI ej **`omi-cli`**, ak kien eo ej jerbal elikin am kakwjarjar ej **`omi`**. Ewor bar juon jikin ko rejjab ejuur etan `omi` ilo PyPI — jab kakkwjarjar jikin in.

Ne `pipx` emoj an kakwjarjar:

```sh
pipx install omi-cli
omi --help
```

Ilo bar juon wewen, ilo juon Python virtual environment eo ej jerbal:

```sh
python -m pip install omi-cli
omi --help
```

Ne terminal eo ejjab loe `omi`, lale bwe virtual environment eo en jerbal ak jikin `pipx` eo ej ped ilo am `PATH`.

## Kobaik am account

Jinoe ippen ri-jiban:

```sh
omi auth login
```

Kālet bwe kwon drelone ilo browser eo, ak kālet am kadrelone Omi developer API key eo. Drelone in ej noje key eo; jab je key eo ilo kien ko renaj ped ilo bwebwenato in terminal eo.

Nan am drelon jimwe ilo browser eo:

```sh
omi auth login --browser
```

Kadrelon ilo computer eo wot me terminal eo ej jerbal ie, kinke anina eo ej jeblak lok nan juon jikin local. Lore nan in kakolkol ko ilo screen eo.

Elikin menin, lale wewen ko im API access eo:

```sh
omi auth status
omi auth whoami
```

`status` ej kwalok jikin local eo im noje men ko rekarbop, ak ejjab kamool ippen server eo. `whoami` ej jilkinklok juon kajjitok emoj anina; tobar melelen bwe peba in kamool ko am rej jerbal jimwe.

Kakwjarjar in ej ped ilo `~/.omi/config.toml`. Jab ajeje peba in kinke ewor am men ko rekarbop ie.

## Lale men ko am

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Juon laajrak ejelok men ie emaron melelen wot bwe ejelok men ko rej koba ippen kajjitok eo. Nan am melele kien ko, lale jiban:

```sh
omi memory list --help
omi action-item list --help
```

## Boke JSON im ukot peij ko

Kojerbal kapit eo `--json` **mokta** jen kien ko:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kien eo moktata ej kajjitok 25 men ko moktata; eo kein karuo ej kajjitok 25 ko tok elikin. Kin menin, juon peij ejjab aolepen men ko. JSON output eo ej kojparok aolepen ID ko, ak table ko remaron kadukadi.

Nan am kojparok juon peij ilo juon file:

```sh
omi --json memory list --limit 25 --offset 0 > kememej-peij-1.json
```

Ukot in ej komman ak ukot juon file ilo jikin eo am. Mokta jen am kojerbal, kamool bwe kien eo ear tobar. Bwid ko rej je ilo stderr; juon file ejelok men ie ejjab kamool bwe ejelok men. Kojparok file in kinke emaron ewor am men ko ie.

## Diwoj (Log out)

```sh
omi auth logout
```

Kien in ej jolok peba in kamool ko rej ped ilo jikin eo. Nan am jolok juon key ilo server eo, kojerbal developer key management ilo am account.

Nan kien ko jet im kapit ko rellap lok, jouj im lale pikinik eo ilo Kajin Belle:
[../README.md](../README.md) im `omi --help`.
