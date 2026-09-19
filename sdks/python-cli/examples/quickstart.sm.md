# Muamua laasaga ma omi-cli

O lenei taiala o loʻo faʻamatalaina ai uluai poloaiga i le gagana Samoa. O igoa o
poloaiga ma feʻau a le polokalame e tumau pea i le faa-Peretania. O faʻataʻitaʻiga o
fesili iinei e le suia au manatuaga, talanoaga, galuega, poʻo sini.

## Faʻapipiʻiina o le polokalame

Manaʻoga: Python 3.10 poʻo se faʻamatalaga fou ma se teugatupe Omi.

Afai o loʻo faʻapipiʻiina lau `pipx`:

```sh
pipx install omi-cli
omi --help
```

E mafai foi ona faʻapipiʻi i totonu o se siosiomaga faʻapitoa (virtual environment)
o le Python:

```sh
python -m pip install omi-cli
omi --help
```

Afai e le maua e le faamalama uliuli (terminal) le `omi`, ia mautinoa o loʻo galue
le siosiomaga faʻapitoa pe o loʻo iai le faila a le `pipx` i lau fesuiaiga `PATH`.

## Fesoʻotaʻi lau teugatupe

Amata le fesoasoani fefaʻasoaaʻi:

```sh
omi auth login
```

Filifili e te ulufale mai e ala i le upega tafaʻilagi (browser) pe faapipii se ki API
a le atinaʻe Omi. O le faʻauluina fefaʻasoaaʻi e natia ai le ki; aloese mai le taina
i totonu o se poloaiga e mafai ona totoe i tala faʻasolopito o le faamalama uliuli.

Ina ia alu saʻo i le upega tafaʻilagi:

```sh
omi auth login --browser
```

Ulufale i luga o le komepiuta lava e tasi o loʻo faʻaogaina ai le faamalama uliuli:
o le tali faʻamaonia e faʻaaogaina ai se tuatusi faʻapitonuʻu. Mulimuli i faatonuga i luga o le lau.

A maeʻa lena, faʻamaonia le faʻatulagaina ma le avanoa i le API:

```sh
omi auth status
omi auth whoami
```

`status` e faʻaalia ai le tulaga faʻapitonuʻu ma natia ai le mealilo, ae le siakiina
lona aoga i luga o le sapalai. `whoami` e auina atu se talosaga faʻamaonia; afai e
manuia, e faʻamaonia ai o loʻo aoga faʻamatalaga ulufale e aunoa ma le faʻaalia o lou igoa.

O le faʻatulagaina e teuina faʻaletonu i le `~/.omi/config.toml`. Aua le faʻasoaina
lenei faila: atonu o loʻo iai au faʻamatalaga ulufale lilo.

## Sailiili i au faʻamaumauga

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

O se lisi gaogao e mafai ona faauigaina e leai ni aitema e fetaui ma le fesili.
Faʻaaoga le fesoasoani e vaʻai ai i faamama mo poloaiga taʻitasi:

```sh
omi memory list --help
omi action-item list --help
```

## Sii mai le JSON ma le faʻasologa o itulau

Tuʻu le filifiliga aoao `--json` **i luma** o le vaega o poloaiga:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

O le poloaiga muamua e fesili mo le uluai 25 manatuaga; o le lona lua mo le isi 25 o sosoo ai.
O se itulau e tasi e le o se kopi faʻasao atoatoa (backup). O le JSON e faʻatumauina
faʻamatalaga faʻapitoa atoatoa, aʻo laulau i luga o le lau e mafai ona faʻapuʻupuʻuina.

Ina ia faʻasaoina se itulau i se faila:

```sh
omi --json memory list --limit 25 --offset 0 > manatuaga-itulau-1.json
```

O lenei faʻatonuga e fausia pe toe tusia le faila faʻapitonuʻu. Ia mautinoa na maeʻa
lelei le poloaiga e aunoa ma ni mea sese aʻo leʻi faʻaaogaina mea o loʻo iai. O mea sese
e tusia i le alavai o mea sese (stderr); o se faila gaogao e le faʻamaonia ai e leai ni faʻamaumauga.
O le faila ua auina atu i fafo e mafai ona aofia ai faʻamatalaga patino: ia teuina faalilolilo.

## Ulufafo (Logout)

```sh
omi auth logout
```

O lenei poloaiga e tapeina ai faʻamatalaga faʻamauina faʻapitonuʻu. Ina ia faʻaleaogaina
se ki i luga o le sapalai, faʻaaoga le pulega o ki atinaʻe i lau teugatupe.

Mo isi poloaiga ma nisi filifiliga faʻapitoa, tagaʻi i
[le taiala autu i le faa-Peretania](../README.md) ma le `omi --help`.
