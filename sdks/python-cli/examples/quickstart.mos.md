# Vɩɩs-n-mik Wilgr omi-cli Yĩnga

Wilgr-kãngã bilgda no-tũudb pipi bõn-naandsã Mòoré (Mossi) gom-biis pʋgẽ `omi-cli` yĩnga. No-tũudb yʋya la porogaramã koees na n kell n zĩnda Ngesẽ gom-biis pʋgẽ. Gesg mamses nins b sẽn wilg ka wã pa toeem y tẽeb (memories), y gom-yensã (conversations), tʋʋm nins sẽn segd n tʋm (action items), bɩ y me-bõones (goals) ye.

## Porogaramã Ningri (Installation)

Sẽn segd n tũ: Python 3.10 bɩ sẽn paas n yaa paalga la Omi kood (account).

Sã n mik tɩ y tara `pipx`:

```sh
pipx install omi-cli
omi --help
```

Y tõe n ning-a-la me Python zĩ-tʋʋmd sẽn tʋmd pʋgẽ (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Sã n mik tɩ `omi` no-tũudb pa yit y ordinatɛɛrã tɛɛrminalẽ ye, bɩ y ges tɩ virtual environment tʋmda bɩ `pipx` zĩiga bee y `$PATH` pʋgẽ.

## Y koodã Lagmeng (Authentication)

Sɩng-y sõngd sẽn gomd ne-yã:

```sh
omi auth login
```

Yãk-y n kẽ ne brawzar (browser) bɩ n ning y Omi developer API key. Kẽer-kãngã sollada y safo; da gʋls-a no-tũudb nins sẽn tõe n kell n zĩnd tɛɛrminalã pĩnd-kibay pʋgẽ wã ye.

Sẽn na yɩl n kẽ brawzarã zĩigẽ tao-tao:

```sh
omi auth login --browser
```

Kẽ-y ordinatɛɛr a yembr ning tɛɛrminalã sẽn tʋmdã zug: sõngr leokrã tũnugda ne zĩ-kãng ladɛrese. Tũ-y tẽeb nins sẽn yaa b sẽn wilg ekranã zugã.

Rẽ poore, bɩ y kãseng bãngr-goamã la API kẽer zĩiga:

```sh
omi auth status
omi auth whoami
```

`status` wilgda zĩ-kãng zĩiga la a solla yel-sollem, la a pa gesd sã n mik tɩ tʋʋmdã kell n bee sɛɛrverã (server) zug ye. `whoami` tʋmda kood b sẽn sakã kotre; sã n yaa ne neer, a wilgda tɩ y zʋrnallã tʋmda tɩ pa tũ ne y yʋʋr wilgri ye.

Bãngr-goamã nong n bĩngda `~/.omi/config.toml` pʋgẽ. Da pʋɩ-y dosiye-kãngã ne neb a taab ye: yel-sollem kood tõe n beeme.

## Y kibayã Gesg (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lisdi sẽn ka tar bũmb võor tõe n yɩɩ bũmb ka be ne y baobrã bala. Tũnug-y ne sõngrã n bãng bõn-yãka no-tũudb a yembr-yembr fãa pʋgẽ:

```sh
omi memory list --help
omi action-item list --help
```

## JSON Paamr la Seb-vãad Pʋgri (Pagination)

Ning-y dũniyã fãa bõn-yãka `--json` **taoore** no-tũudb sullã taoore:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pipi no-tũudbã kota tẽeb 25 pipi rãmba; a yiib-n-soabã kota 25 nins sẽn pʋgdã. Seb-vãamb a yembr pa kibay fãa bĩngr (backup) ye. JSON yitda rɩka yʋy fãa n bĩng zãng-zãng, baa ekranã taablã sã n tõe n bilga a waoongã.

Sẽn na yɩl n bĩng seb-vãamb dosiye pʋgẽ:

```sh
omi --json memory list --limit 25 --offset 0 > teeb-seb-vaamb-1.json
```

Sõngr-kãngã meegda bɩ n toeemd dosiye zĩ-kãng pʋgẽ. Ges-y tɩ no-tũudbã sa ne neer tɩ y nan pa tũnug ne bũmb ning sẽn be a pʋgẽ wã ye. Bõn-wẽns gʋlsda bõn-wẽns yit zĩigẽ (stderr); dosiye sẽn ka tar bũmb pa wilgd tɩ kibay ka be ye. Dosiye ning y sẽn yiisã tõe n tara y meng kibaya: gũ-y a neere.

## Yiyr koodã pʋgẽ (Logout)

```sh
omi auth logout
```

No-tũudb-kãngã yiisda kood nins b sẽn bĩng zĩ-kãng pʋgẽ wã. Sẽn na yɩl n menok safo sɛɛrverã zugã, tũnug-y ne developer key yel-gesg y koodã pʋgẽ.

No-tũudb a taab la bõn-yãk a taab yĩnga, ges-y [Ngesẽ wilgr kãsengã](../README.md) la `omi --help`.
