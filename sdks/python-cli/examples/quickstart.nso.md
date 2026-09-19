# Tlhahlo e Kopana ya omi-cli

Tlhahlo ye e hlaloša ditaelo tša mathomo ka Sepedi (Northern Sotho) tša `omi-cli`. Maina a ditaelo le melaetša ya lenaneo di dula di ngwadilwe ka Seisimane. Mehlala ya go hlahloba ye e laeditšwego mo ga e fetole dikgopolo tša gago (memories), dipoledišano (conversations), mediro ye e swanetšego go dirwa (action items), goba maikemišetšo a gago (goals).

## Go tsenya lenaneo (Installation)

Dinyakwa: Python 3.10 goba ye mpsha kudu le akhaonto ya Omi.

Ge eba o šetše o na le `pipx`:

```sh
pipx install omi-cli
omi --help
```

O ka e tsenya gape ka gare ga tikologo ye e šomago ya Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ge taelo ya `omi` e sa hwetšagale theminaleng, kgonthiša gore virtual environment e a šoma goba gore tsela ya `pipx` e ka gare ga `$PATH` ya gago.

## Go kgokaganya akhaonto ya gago (Authentication)

Thoma mothuši yo a boledišanago le wena:

```sh
omi auth login
```

Kgetha go tsena ka go šomiša sefetleki sa inthanete (browser) goba go ngwala Omi developer API key ya gago. Mokgwa wo o fihla senotlelo se; o se ke wa se ngwala ditaelong tše di ka šalago historing ya theminale.

Go ya thwii sefetleking sa inthanete:

```sh
omi auth login --browser
```

Tsena khomphutheng e tee yeo theminale e šomago go yona: karabo ya netefatšo e šomiša aterese ya legae. Latela ditaelo tše di lego sekrineng.

Ka morago ga fao, netefatša peakanyo le phihlelelo ya API:

```sh
omi auth status
omi auth whoami
```

`status` e bontšha seemo sa legae gomme e fihla diphiri, efela ga e hlahlobe ge eba e sa šoma go sethusi (server). `whoami` e romela kgopelo ye e netefaditšwego; ge e atlegile, e tiišetša gore ditokomane di a šoma ntle le go bontšha leina la gago.

Dipeakanyo di bolokwa gantši go `~/.omi/config.toml`. O se ke wa abelana faele ye: e ka ba e na le ditokomane tša sephiri.

## Go hlahloba datha ya gago (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lethathamo le le se nago selo le ka bolela fela gore ga go na se se nyalelanago le dinyakišišo. Šomiša thušo go hwetša dikgetho taelong e nngwe le e nngwe:

```sh
omi memory list --help
omi action-item list --help
```

## Go hwetša JSON le go aba Matlakala (Pagination)

Bea kgetho ya lefase ka bophara ya `--json` **pele** ga sehlopha sa ditaelo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Taelo ya mathomo e kgopela dikgopolo tša mathomo tše 25; ya bobedi e kgopela tše 25 tše di latelago. Letlakala le le tee ga se polokelo ye e feletšego (backup). Datha ya JSON e boloka dišupo ka moka, le ge tafola ya sekrine e ka di fokotša go di bontšha gabotse.

Go boloka letlakala faeleng:

```sh
omi --json memory list --limit 25 --offset 0 > dikgopolo-letlakala-1.json
```

Tsela ye e hlama goba ya fetoša faele ya legae. Kgonthiša gore taelo e phethilwe gabotse pele o šomiša se se lego ka gare. Diphošo di ngwalwa karolong ya diphošo (stderr); faele ye e se nago selo ga e reye gore ga go na datha. Faele ye e ntšhitšwego e ka ba le tshedimošo ya gago ya sephiri: e boloke ka šedi.

## Go tšwa akhaontong (Logout)

```sh
omi auth logout
```

Taelo ye e tloša ditokomane tše di bolokilwego lefelong la legae. Go phumola senotlelo sethusing, šomiša taolo ya developer key akhaontong ya gago.

Go hwetša ditaelo tše dingwe le dikgetho tše di oketšegilego, bona [tlhahlo e kgolo ya Seisimane](../README.md) le `omi --help`.
