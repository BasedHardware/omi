# omi-cli bilen Çalt Başlangyç

Bu gollanma türkmen dilinde başlangyç buýruklary düşündirýär. Buýruklaryň atlary we programma habarlary iňlis dilinde galýar. Bu ýerde görkezilen sorag (query) mysallary ýatlaryňyzy (memories), söhbetdeşlikleriňizi (conversations), ýerine ýetirilmeli işleriňizi (action items) ýa-da maksatlaryňyzy (goals) üýtgetmeýär.

## Programmany gurnamak (Installation)

Talaplar: Python 3.10 ýa-da has täze wersiýasy we Omi hasaby.

Eger sizde `pipx` gurnalan bolsa:

```sh
pipx install omi-cli
omi --help
```

Başga bir usul hökmünde, ony işjeň Python wirtual gurşawynyň (virtual environment) içinde gurnap bilersiňiz:

```sh
python -m pip install omi-cli
omi --help
```

Eger terminal `omi` buýrugyny tapmasa, wirtual gurşawyň işjeňdigine ýa-da `pipx` guralynyň faýllary ýerleşdirýän bukjanyň `$PATH` ulgamyňyzda bardygyna göz ýetiriň.

## Hasabyňyzy birikdirmek (Authentication)

Gepleşik kömekçisini (interactive assistant) başladyň:

```sh
omi auth login
```

Brauzer arkaly girmegi ýa-da Omi developer API açaryny goýmagy saýlaň. Bu usul açary gizleýär; açary terminal taryhynda galyp biljek buýrukda ýazmakdan gaça duruň.

Göni brauzere geçmek üçin:

```sh
omi auth login --browser
```

Terminalyň işleýän kompýuterinde giriň: tassyklama jogaby ýerli salgyny (local address) ulanýar. Ekranda peýda bolýan görkezmelere eýeriň.

Ondan soň, sazlamalary we API elýeterliligini barlaň:

```sh
omi auth status
omi auth whoami
```

`status` ýerli ýagdaýy görkezýär we gizlin maglumatlary ýapýar, emma serwerde dogrulygyny barlamaýar. `whoami` tassyklanan haýyş iberýär; eger üstünlikli bolsa, adyňyzy görkezmezden şahsy maglumatlaryňyzyň işleýändigini tassyklaýar.

Sazlamalar adatça `~/.omi/config.toml` faýlynda saklanýar. Bu faýly başgalar bilen paýlaşmaň, sebäbi onda gizlin ygtyýarnamalaryňyz bolup biler.

## Maglumatlaryňyzy gözden geçirmek

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Boş sanaw diňe soraga gabat gelýän zatlaryň ýokdugyny aňladyp biler. Her buýrukdaky süzgüçleri görmek üçin kömek bölümini ulanyň:

```sh
omi memory list --help
omi action-item list --help
```

## JSON almak we sahypalar boýunça geçmek (Pagination)

Ähliumumy `--json` opsiýasyny buýruklar toparyndan **öň** goýuň:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Birinji buýruk ilkinji 25 ýady sorar; ikinjisi, indiki 25 ýady. Ýeke sahypa doly ätiýaçlyk nusgasy (backup) däldir. JSON çykyşy ähli kesgitleýjileri doly saklaýar, ekrandaky tablisalar bolsa aňsat görmek üçin olary gysgaldyp biler.

Sahypany faýla ýazdyrmak üçin:

```sh
omi --json memory list --limit 25 --offset 0 > yatlar-sahypa-1.json
```

Bu gönükdirme ýerli faýly döredýär ýa-da çalşyrýar. Mazmuny ulanmazdan ozal buýrugyň üstünlikli tamamlanandygyna göz ýetiriň. Ýalňyşlyklar ýalňyşlyk çykyşyna (stderr) ýazylýar; boş faýl maglumatyň ýokdugyna kepil geçmeýär. Eksport edilen faýlda şahsy maglumatlar bolup biler: ony ygtybarly saklaň.

## Hasapdan çykmak (Logout)

```sh
omi auth logout
```

Bu buýruk ýerli saklanýan şahsy maglumatlary aýyrýar. Açary serwerde ýatyrmak üçin hasabyňyzdaky dörediji açarlary dolandyryş bölümini ulanyň.

Başga buýruklar we giňişleýin mümkinçilikler üçin [iňlis dilindäki esasy gollanma](../README.md) we `omi --help` serediň.
