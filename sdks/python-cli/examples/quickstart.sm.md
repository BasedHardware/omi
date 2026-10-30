# O laasaga muamua ma le omi-cli

O lenei taʻiala o loʻo faʻamatalaina ai laasaga muamua (commands) a le omi-cli i le gagana Samoa. O igoa o poloaiga ma feʻau a le polokalame e tumau i le Igilisi. O faʻataʻitaʻiga suʻesuʻe o loʻo faʻaalia iinei e le suia ai ou manatuaga (memories), au talanoaga (conversations), au galuega (action items) poʻo au sini (goals).

## Faʻapipiʻiina

E manaʻomia: Python 3.10 pe sili atu, ma se teugatupe Omi.

Afai e iai sau `pipx`:

```sh
pipx install omi-cli
omi --help
```

E mafai foʻi ona e faʻapipiʻiina i totonu o se siosiomaga Python faʻapitoa o loʻo galue:

```sh
python -m pip install omi-cli
omi --help
```

Afai e le maua e le terminal le `omi`, ia mautinoa o loʻo galue le siosiomaga faʻapitoa pe o loʻo i totonu o le `$PATH` le faila o le `pipx`.

## Faʻafesoʻotaʻi lau teugatupe

Amata le fesoasoani faʻafesoʻotaʻi:

```sh
omi auth login
```

Filifili e ulufale i le browser pe faʻapipiʻi se ki API a le Omi developer. O le faʻaogaina faʻafesoʻotaʻi e natia ai le ki; aloese mai le tusiaina i se poloaiga e teuina i le talafaasolopito o le terminal.

Ina ia alu saʻo i le browser:

```sh
omi auth login --browser
```

Ulufale i le komepiuta lava lea e tasi ma le terminal: o le tali faʻamaonia e alu i le tuatusi faʻapitonuʻu. Mulimuli i faatonuga i luga o le lau.

A maeʻa, siaki le faatulagaga ma le avanoa API:

```sh
omi auth status
omi auth whoami
```

`status` e faʻaalia ai le tulaga faʻapitonuʻu ma natia ai le mealilo, ae e le siakia le aoga i le server. `whoami` e faia se talosaga faʻamaonia; afai e manuia, e manino lava o loʻo galue faʻamaumauga, e aunoa ma le faʻaalia o lou igoa.

O le faatulagaga e teuina e ala i le faaletonu i `~/.omi/config.toml`. Aua le faʻasoa lenei faila: e mafai ona i ai faʻamaumauga faalilolilo.

## Suʻesuʻe au faʻamaumauga

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

O se lisi avanoa e masani lava ona uiga e leai se mea e fetaui ma le suʻesuʻega. Faaaoga le fesoasoani e suʻe ai vaega o poloaiga taitasi:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ma itulau

Tuu le filifiliga aoao `--json` **i luma** o le vaega o poloaiga:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

O le poloaiga muamua e talosaga mo manatuaga 25 muamua; o le lona lua mo le isi 25. E le o se kopi atoa le itulau e tasi. O le JSON e tausia ai numera atoa, ae o laulau i luga o le lau e mafai ona faʻapuupuuina.

Ina ia teuina se itulau i se faila:

```sh
omi --json memory list --limit 25 --offset 0 > manatuaga-itulau-1.json
```

O lenei faʻasologa e fatuina pe toe tusiina se faila faʻapitonuʻu. Ia mautinoa ua maeʻa le poloaiga ae e te leʻi faʻaaogaina le anotusi. O mea sese e tusia i le faila o mea sese (stderr); o se faila avanoa e le o se faamaoniga e leai ni faamaumauga. O se faila e auina atu i fafo e mafai ona i ai faamatalaga patino: teuina faalilolilo.

## Saini ese

```sh
omi auth logout
```

O lenei poloaiga e tapeina faamaumauga o loʻo teuina i le lotoifale. Ina ia faalēaogāina se ki i le server, faaaoga le pulega o ki developer i lau lava teugatupe.

Mo nisi poloaiga ma filifiliga, vaai le [taʻiala autu i le Igilisi](../README.md) ma le `omi --help`.
