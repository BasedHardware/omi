# A' chiad cheumannan le omi-cli

Tha an stiùireadh seo a' toirt a' chiad cheumannan le omi-cli anns a' Ghàidhlig. Tha ainmean nan òrdughan agus teachdaireachdan a' phrògraim a' fuireach anns a' Bheurla. Chan atharraich na h-eisimpleirean anns an stiùireadh seo do chuimhneachain, do chòmhraidhean, na nithean-gnìomha no na targaidean agad.

## Stàladh

Feumaidh tu Python 3.10 no nas ùire, agus cunntas Omi.

Ma tha `pipx` air a stàladh mu thràth:

```sh
pipx install omi-cli
omi --help
```

Mur eil, stàlaich e ann an àrainneachd bheartach Python a tha gnìomhach:

```sh
python -m pip install omi-cli
omi --help
```

Mura lorg an terminal `omi`, thoir sùil a bheil an àrainneachd bheartach gnìomhach no a bheil eòlaire pipx ann an `$PATH`.

## Ceangail do chunntas

Tòisich an draoidh-clàraidh eadar-ghnìomhach:

```sh
omi auth login
```

'S urrainn dhut clàradh a-steach leis a' bhrobhsair no iuchair API leasaiche Omi a chur ann. Bidh an clàradh eadar-ghnìomhach a' falach d' iuchair; bi faiceallach nach fàg thu ann an eachdraidh an terminal e.

Airson clàradh a-steach gu dìreach leis a' bhrobhsair:

```sh
omi auth login --browser
```

Clàraich a-steach air an aon choimpiutar air a bheil an terminal a' ruith: bidh am freagairt ùghdarrachaidh a' cleachdadh seòladh ionadail. Lean an stiùireadh air an sgrion.

Thoir sùil a-nis air an rèiteachadh agus an iuchair API:

```sh
omi auth status
omi auth whoami
```

Bidh `status` a' sealltainn na stàite ionadail agus a' falach dhìomhairean, ach cha dèan e sgrùdadh leis an t-seirbheisiche. Bidh `whoami` a' dèanamh iarraidh ùghdarraichte; ma shoirbhicheas leis, bidh e a' dearbhadh gu bheil an ùghdarrachadh agad ag obair, ach cha seall e d' ainm.

Tha an rèiteachadh ann an `~/.omi/config.toml`. Na roinn am faidhle seo: dh'fhaodadh dìomhairean clàraidh a bhith ann.

## Sgrùdadh dàta

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Dh'fhaodadh liosta falamh a bhith a' ciallachadh dìreach nach eil dàta ann a fhreagras don cheist. Ionnsaich criathragan gach òrduigh leis a' chobhair:

```sh
omi memory list --help
omi action-item list --help
```

## Toradh JSON agus pagination

Cuir an roghainn chruinneil `--json` **mus** a' bhuidheann-òrduigh:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Bidh a' chiad òrdugh a' faighinn a' chiad 25 cuimhneachain; bidh an dàrna òrdugh a' faighinn an ath 25. Gu tric chan eil aon duilleag làn. Bidh toradh JSON a' gleidheadh a h-uile aithnichear, ach bidh clàran air an sgrion gam gearradh gu tric.

Airson duilleag a sgrìobhadh gu faidhle:

```sh
omi --json memory list --limit 25 --offset 0 > cuimhneachain-duilleag-1.json
```

Bidh ath-stiùireadh a' cruthachadh no a' sgrìobhadh thairis air faidhle ionadail. Thoir sùil a bheil an t-òrdugh air soirbheachadh mus cleachd thu an t-susbaint. Bidh mearachdan a' dol gu stderr; chan eil faidhle falamh a' ciallachadh nach eil dàta ann. Dh'fhaodadh fiosrachadh prìobhaideach a bhith ann am faidhlichean a chaidh an cur a-mach: cùm iad gu sàbhailte.

## Clàradh a-mach

```sh
omi auth logout
```

Bidh an t-òrdugh seo a' toirt air falbh an ùghdarrachadh ionadail a chaidh a shàbhaladh. Airson an iuchair a chur air ais air an t-seirbheisiche, cleachd rianachd nan iuchraichean leasaiche air do chunntas.

Airson barrachd òrdughan agus roghainnean adhartach, faic an [Iùl mòr na Beurla](../README.md) agus `omi --help`.
