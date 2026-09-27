# A' chiad cheuman le omi-cli

Tha an stiùireadh seo ag innse mu chiad àitheantan (commands) omi-cli sa Ghàidhlig. Fuirichidh ainmean nan àitheantan agus teachdaireachdan a' phrògraim sa Bheurla. Chan atharraich na h-eisimpleirean rannsachaidh a tha air an sealltainn an seo do chuimhne (memories), do chòmhraidhean (conversations), na nithean-gnìomha agad (action items) no na h-amasan agad (goals).

## An stàladh

Feumalachdan: Python 3.10 no nas ùire, agus cunntas Omi.

Ma tha `pipx` agad:

```sh
pipx install omi-cli
omi --help
```

Faodaidh tu cuideachd a stàladh ann an àrainneachd bheartail Python a tha gnìomhach:

```sh
python -m pip install omi-cli
omi --help
```

Mura lorg an t-terminal `omi`, dèan cinnteach gu bheil an àrainneachd bheartail gnìomhach no gu bheil pasgan `pipx` air `$PATH`.

## Do chunntas a cheangal

Tòisich an neach-cuideachaidh eadar-ghnìomhach:

```sh
omi auth login
```

Tagh clàradh a-steach tron bhrabhsair no cuir a-steach iuchair API leasaiche Omi. Bidh cuir a-steach eadar-ghnìomhach a' falach na h-iuchrach; seachain a sgrìobhadh ann an àithne a thèid a shàbhaladh ann an eachdraidh an terminal.

Gus a dhol gu dìreach don bhrabhsair:

```sh
omi auth login --browser
```

Clàraich a-steach air an aon choimpiutar ris an terminal: thèid am freagairt dearbhaidh chun t-seòladh ionadail. Lean an stiùireadh air an sgrion.

Às dèidh sin, faodaidh tu an rèiteachadh agus inntrigeadh API a dhearbhadh:

```sh
omi auth status
omi auth whoami
```

Bidh `status` a' sealltainn an staid ionadail agus a' falach an dìomhaireachd, ach chan eil e a' dearbhadh dligheachd air an fhrithealaiche. Nì `whoami` iarrtas dearbhaichte; ma shoirbhicheas leis, tha e soilleir gu bheil na teisteanasan ag obair, gun d'ainm a nochdadh.

Thèid an rèiteachadh a shàbhaladh gu bunaiteach ann an `~/.omi/config.toml`. Na roinn am faidhle seo: dh'fhaodadh teisteanasan dìomhair a bhith ann.

## Do dhàta a rannsachadh

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tha liosta falamh gu tric a' ciallachadh dìreach nach eil dad a' freagairt don rannsachadh. Cleachd a' chuideachadh gus na criathran airson gach àithne a lorg:

```sh
omi memory list --help
omi action-item list --help
```

## JSON agus duilleagachadh

Cuir an roghainn chruinneil `--json` **roimhe** a' bhuidheann àitheantan:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Bidh a' chiad àithne ag iarraidh a' chiad 25 cuimhne; bidh an dàrna tè ag iarraidh an ath 25. Chan e duilleag aon leth-bhreac iomlan. Bidh toradh JSON a' gleidheadh àireamhan slàn, fhad 's a dh'fhaodas clàran air an sgrion an giorrachadh.

Gus duilleag a shàbhaladh ann am faidhle:

```sh
omi --json memory list --limit 25 --offset 0 > cuimhnean-duilleag-1.json
```

Bidh an ath-sheòladh seo a' cruthachadh no a' sgrìobhadh thairis air faidhle ionadail. Dèan cinnteach gu bheil an àithne deiseil mus cleachd thu an susbaint. Thèid mearachdan a sgrìobhadh chun toradh mearachd (stderr); chan eil faidhle falamh na dhearbhadh nach eil dàta ann. Dh'fhaodadh fiosrachadh pearsanta a bhith ann am faidhle a chaidh a thoirt a-mach: cùm prìobhaideach e.

## Clàradh a-mach

```sh
omi auth logout
```

Bidh an àithne seo a' sguabadh às na teisteanasan a chaidh an sàbhaladh gu h-ionadail. Gus iuchair air an fhrithealaiche a chur à bith, cleachd riaghladh nan iuchraichean leasaiche air do chunntas fhèin.

Airson barrachd àitheantan agus roghainnean, faic [am prìomh stiùireadh sa Bheurla](../README.md) agus `omi --help`.
