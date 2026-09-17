# L-Ewwel Passi b'omi-cli

Din il-gwida tispjega l-ewwel kmandi bil-Malti. L-ismijiet tal-kmandi u
l-messaġġi tal-programm jibqgħu bl-Ingliż. L-eżempji ta' mistoqsijiet li jidhru
hawnhekk ma jimmodifikawx il-memorji, il-konversazzjonijiet, il-kompiti jew
l-għanijiet tiegħek.

## Installa l-programm

Rekwiżiti: Python 3.10 jew verżjoni aktar reċenti u kont ta' Omi.

Jekk għandek `pipx` installat:

```sh
pipx install omi-cli
omi --help
```

Bħala alternattiva, tista' tinstallah ġewwa ambjent virtwali ta' Python
attivat:

```sh
python -m pip install omi-cli
omi --help
```

Jekk it-terminal ma jsibx `omi`, iċċekkja li l-ambjent virtwali huwa attivat
jew li d-direttorju fejn `pipx` jinstalla l-eżekutibbli tiegħu qiegħed fil-`PATH`
tiegħek.

## Qabbad il-kont tiegħek

Ibda l-assistent interattiv:

```sh
omi auth login
```

Agħżel li tidħol permezz tal-brawżer jew l-għażla li twaħħal API key tal-iżviluppatur
ta' Omi. L-input interattiv jaħbi l-muftieħ; evita li tiktbu f'kmand li jibqa'
fl-istorja tat-terminal.

Biex tmur direttament fil-brawżer:

```sh
omi auth login --browser
```

Idħol fuq l-istess kompjuter bħat-terminal: it-tweġiba tal-awtentikazzjoni
tuża indirizz lokali. Segwi l-istruzzjonijiet li jidhru fuq l-iskrin.

Wara, ivverifika l-konfigurazzjoni u l-aċċess għall-API:

```sh
omi auth status
omi auth whoami
```

`status` juri l-istat lokali u jaħbi s-sigriet, iżda ma jiċċekkjax il-validità
fuq is-server. `whoami` jagħmel talba awtentikata; jekk tirnexxi, tikkonferma
li l-kredenzjali jaħdmu, mingħajr ma bilfors turi ismek.

Il-konfigurazzjoni tiġi ffrankata f'`~/.omi/config.toml` b'mod awtomatiku.
Taqsamx dan il-fajl: jista' jkun fih il-kredenzjali tiegħek.

## Ikkonsulta d-dejta tiegħek

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lista vojta tista' sempliċement tfisser li m'hemm l-ebda oġġett li jaqbel
mal-mistoqsija. Uża l-għajnuna biex tiskopri l-filtri ta' kull kmand:

```sh
omi memory list --help
omi action-item list --help
```

## Ikseb JSON u nnaviga fil-paġni

Poġġi l-għażla globali `--json` **qabel** il-grupp ta' kmandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

L-ewwel kmand jitlob l-ewwel 25 memorja; it-tieni wieħed, il-25 li jmiss.
Paġna waħda għalhekk mhijiex kopja ta' riżerva sħiħa. Il-produzzjoni ta' JSON
iżżomm l-identifikaturi sħaħ, filwaqt li t-tabelli jistgħu jqassruhom għall-wiri.

Biex tissejvja paġna f'fajl:

```sh
omi --json memory list --limit 25 --offset 0 > memorji-pagna-1.json
```

Dan ir-ridirezzjonament joħloq jew jissostitwixxi l-fajl lokali. Ivverifika li
l-kmand spiċċa b'suċċess qabel ma tuża l-kontenut tiegħu. L-iżbalji jinkitbu
fl-output tal-iżbalji; fajl vojt ma jiggarantixxix li m'hemmx dejta. Il-fajl
esportat jista' jkun fih informazzjoni personali: żommu privat.

## Oħroġ mis-sistema (Logout)

```sh
omi auth logout
```

Dan il-kmand iħassar il-kredenzjali ffrankati lokalment. Biex tirrevoka muftieħ
fuq is-server, uża l-immaniġġjar tal-imfietaħ tal-iżviluppatur fil-kont tiegħek.

Għall-kumplament tal-kmandi u għażliet avvanzati, ikkonsulta l-
[gwida prinċipali bl-Ingliż](../README.md) u `omi --help`.
