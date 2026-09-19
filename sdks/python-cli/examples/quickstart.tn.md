# Kaedi e e Bonako ya omi-cli

Kaedi e e tlhalosa ditaelo tsa ntlha ka Setswana sa `omi-cli`. Maina a ditaelo le melaetsa ya lenaneo a sala a le ka Seesimane. Dikao tsa go batlisisa tse di bontshitsweng fa ga di fetole dikgopotso tsa gago (memories), dipuisano (conversations), ditiro tse di tshwanetseng go dirwa (action items), kgotsa maikemisetso (goals).

## Go tsenya lenaneo (Installation)

Ditlhokego: Python 3.10 kgotsa e e ntshafaditsweng le akhaonto ya Omi.

Fa o setse o na le `pipx`:

```sh
pipx install omi-cli
omi --help
```

Gape o ka e tsenya mo tikologong e e dirang ya Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Fa taelo ya `omi` e sa bonale mo theminaleng, netefatsa gore virtual environment e a dira kgotsa gore tsela ya `pipx` e mo teng ga `$PATH` ya gago.

## Go golaganya akhaonto ya gago (Authentication)

Simolola mothusi yo o buisanang le wena:

```sh
omi auth login
```

Tlhopha go tsena ka go dirisa sebatli sa inthanete (browser) kgotsa go manega Omi developer API key ya gago. Tsela e e fithang senotlolo se; o se ka wa se kwala mo ditaelong tse di ka salang mo hisitoring ya theminale.

Go ya tlhamalalo kwa sebatling sa inthanete:

```sh
omi auth login --browser
```

Tsena mo khomphuteng e le nngwe e theminale e dirang mo go yone: karabo ya netefatso e dirisa aterese ya selegae. Latela ditaelo tse di mo sekirining.

Morago ga moo, netefatsa diphetogo le phitlhelelo ya API:

```sh
omi auth status
omi auth whoami
```

`status` e bontsha seemo sa selegae mme e fitha diphiri, mme ga e tlhatlhobe fa se ntse se bereka kwa go sefepi (server). `whoami` e romela kopo e e netefaditsweng; fa e atlegile, e netefatsa gore ditokomane di a bereka ntle le go bontsha leina la gago.

Dithulaganyo di bewa ka tlwaelo mo `~/.omi/config.toml`. O se ka wa abelana faele e le batho ba bangwe: e ka tswa e tshotse ditokomane tsa sephiri.

## Go tlhatlhoba tshedimosetso ya gago (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lenaane le le se nang sepe le ka kaya fela gore ga go na sepe se se tsamaisanang le patlo. Dirisa thuso go bona dithulaganyo mo taelong nngwe le nngwe:

```sh
omi memory list --help
omi action-item list --help
```

## Go tsaya JSON le Kgaoganyo ya Ditsebe (Pagination)

Tsenya tlhopho ya lefatshe ya `--json` **pele** ga setlhopha sa ditaelo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Taelo ya ntlha e kopa dikgopotso tsa ntlha tse 25; ya bobedi e kopa tse 25 tse di latelang. Tsebe e le nngwe ga se polokelo e e feletseng (backup). Tshedimosetso ya JSON e boloka boitshupo jotlhe, le fa tafole ya sekirini e ka di khutsofatsa go di bontsha sentle.

Go boloka tsebe mo faeleng:

```sh
omi --json memory list --limit 25 --offset 0 > dikgopotso-tsebe-1.json
```

Tsela e e bopa kgotsa e fetola faele ya selegae. Netefatsa gore taelo e weditswe sentle pele o dirisa se se mo teng. Diphoso di kwalwa mo karolong ya diphoso (stderr); faele e e senang sepe ga e reye gore ga go na tshedimosetso. Faele e e ntshitsweng e ka nna le tshedimosetso ya gago ya sephiri: e boloke ka tlhokomelo.

## Go tswa mo akhaontong (Logout)

```sh
omi auth logout
```

Taelo e e tlosa ditokomane tse di bolokilweng mo lefelong la selegae. Go phimola senotlolo kwa sefeping, dirisa tsamaiso ya developer key mo akhaontong ya gago.

Go bona ditaelo tse dingwe le dikgetho tse di oketsegileng, bona [kaedi e kgolo ya Seesimane](../README.md) le `omi --help`.
