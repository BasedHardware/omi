# Amata faʻaaoga le omi-cli

O lenei taʻiala e faʻaalia ai nai faʻatonuga muamua i le Gagana Samoa. O igoa o faʻatonuga ma feʻau a le faiga e tumau pea i le faʻaPeretania. O faʻataʻitaʻiga faitau o loʻo aumaia iinei o le a le suia ai au faʻamaumauga, talanoaga, lisi o galuega poʻo sini.

## Faʻapipiʻi le polokalame

Manaʻoga: Python 3.10 poʻo se faʻamatalaga fou ma se teugatupe Omi.

> Faʻalogo: O le igoa o le afifi i luga o le PyPI o le **`omi-cli`**, ae o le faʻatonuga e faʻatautaia pe a maeʻa ona faʻapipiʻi o le **`omi`**. O loʻo i ai se afifi ese e le fesoʻotaʻi e igoa ia `omi` ile PyPI — aua le faʻapipiʻiina lena afifi.

Afai ua faʻapipiʻiina le `pipx`:

```sh
pipx install omi-cli
omi --help
```

I se isi itu, i totonu o se siosiomaga tafailagi Python o loʻo ola:

```sh
python -m pip install omi-cli
omi --help
```

Afai e le maua e le terminal le `omi`, ia mautinoa o loʻo galue le siosiomaga tafailagi pe o iai le lisi o le `pipx` i lau `PATH`.

## Fesoʻotaʻi lau teugatupe

Amata le fesoasoani fegalegaleai:

```sh
omi auth login
```

Filifili e saini e ala i le upega tafaʻilagi, pe filifili le filifiliga e faʻapipiʻi le ki API o le fausiaina Omi. O le faʻaulu fegalegaleai e natia ai le ki; aua le taina le ki i faʻatonuga e mafai ona tumau i le tala faʻasolopito o le terminal.

Mo le saini saʻo i le upega tafaʻilagi:

```sh
omi auth login --browser
```

Faʻauma le saini i luga o le komepiuta lava e tasi o loʻo faʻagasolo ai le terminal, aua o le faʻamaoniga e toe foʻi i se tuatusi faʻapitonuʻu. Mulimuli i faʻatonuga o loʻo faʻaalia i luga o le lau.

A maeʻa lena, siaki le faʻatulagaga ma le avanoa i le API:

```sh
omi auth status
omi auth whoami
```

O le `status` e faʻaalia ai le tulaga faʻapitonuʻu ma natia mealilo, ae le faʻamaonia ma le server. O le `whoami` e auina atu se talosaga faʻamaonia; o le manuia o lona uiga o loʻo lelei le faʻaaogaina o au faʻamaoniga.

O le faʻatulagaga e teuina faʻaletonu i le `~/.omi/config.toml`. Aua le faʻasoaina lenei faila aua o loʻo iai au faʻamatalaga patino.

## Vaʻai au faʻamaumauga

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

O se lisi gaogao e naʻo le uiga e leai ni mea e fetaui ma lau fesili. Ina ia iloa faʻamama o se faʻatonuga, vaʻai le fesoasoani:

```sh
omi memory list --help
omi action-item list --help
```

## Aumai le JSON ma liliu itulau

Tuʻu le filifiliga lautele `--json` **aʻo leʻi** faia le vaega o faʻatonuga:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

O le faʻatonuga muamua e talosagaina ai faʻamaumauga e 25 muamua; o le lona lua e talosagaina ai le isi 25 o loʻo sosoʻo mai. O le mea lea, o le tasi itulau e le o se kopi atoatoa. O le JSON output e teuina faʻamatalaga atoatoa, aʻo laulau e mafai ona faʻapuʻupuʻuina.

Ina ia teuina se itulau i se faila:

```sh
omi --json memory list --limit 25 --offset 0 > faamaumauga-itulau-1.json
```

O lenei faʻafeiloaʻiga e fatuina pe suia ai se faila i le lotoifale. Aʻo leʻi faʻaaogaina mea o loʻo i ai, ia mautinoa na manuia le faʻatonuga. O mea sese e tusia i le stderr; o se faila gaogao e le o se faʻamaoniga e leai ni faʻamaumauga. O le faila na teuina e mafai ona iai ni faʻamatalaga patino: ia faʻamautinoa le saogalemu.

## Alu i fafo (Log out)

```sh
omi auth logout
```

O lenei faʻatonuga e aveese ai faʻamaoniga o loʻo teuina i le lotoifale. Ina ia faʻaleaogaina se ki i luga o le server, faʻaaoga le pulega o ki a le fausiaina i lau teugatupe.

Mo isi faʻatonuga ma filifiliga maualuluga, faʻamolemole tagaʻi i le taʻiala autu i le faʻaPeretania:
[../README.md](../README.md) ma le `omi --help`.
