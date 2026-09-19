# Okutandika Amangu n'enkola ya omi-cli

Obulagirizi buno bunnyonnyola ebiragiro ebisookerwako mu lulimi Oluganda (Luganda). Amannya g'ebiragiro n'obubaka okuva mu pulogulaamu bisigala mu Lungereza. Ebyokulabirako eby'okubuuza (query) ebiragiddwa wano tebikyuusa bijjukizo byo (memories), emboozi zo (conversations), ebyokukola (action items), oba ebiruubirirwa byo (goals).

## Okuteeka pulogulaamu ku kompyuta (Installation)

Ebyetaagisa: Python 3.10 oba enkola empya n'akawunti ya Omi.

Bw'oba nga walina `pipx` eteekeddwako dda:

```sh
pipx install omi-cli
omi --help
```

Engeri endala, osobola okugiteeka mu mbeera ya Python virtual environment ekozesebwa mu kaseera kano:

```sh
python -m pip install omi-cli
omi --help
```

Terminal bw'eba tefunye `omi`, kakasa nti virtual environment ekola oba nti etterekero lya fayiro za `pipx` liri mu `$PATH` yo.

## Okugatta akawunti yo (Authentication)

Tandika omuyambi ow'ebyokusoma (interactive assistant):

```sh
omi auth login
```

Londawo okuyingira ng'okozesa browser oba eky'okukoppa n'okuteekamu ebisumuluzo bya developer API key ebya Omi. Enkola eno ekweka ebisumuluzo; weewale okuwandiika ebisumuluzo mu kiragiro ekiyinza okusigala mu byafaayo bya terminal.

Okugenda butereevu mu browser:

```sh
omi auth login --browser
```

Yingira ku kompyuta y'emu ng'eyo terminal kw'ekolera: okukakasa kukozesa ndagiriro ey'ekitundu (local address). Goberera ebiragiro ebiri ku screen.

Oluvannyuma lw'ekyo, kenneenya enteekateeka n'obuyinza bw'okukozesa API:

```sh
omi auth status
omi auth whoami
```

`status` eraga embeera ey'ekitundu n'ekweka ebyama, naye tekebera butuufu ku server. `whoami` etuma okusaba okukakasiddwa; bwe kiba kiyiseemu, kiba kikakasa nti ebisumuluzo bikola awatali kussaako linnya lyo.

Enteekateeka zikuumibwa nga bwe ziri mu `~/.omi/config.toml`. Tosaasaanya fayiro eno kubanga eyinza okubaamu ebyama byo eby'ekikugu.

## Okukenneenya data yo

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Olukalala olutaliiko kintu luyinza okuba nga lutegeeza bulala nti tewali bintu bituukana na kusaba kwo. Kozesa obuyambi okusobola okulaba eby'okusunsulamu ku buli kiragiro:

```sh
omi memory list --help
omi action-item list --help
```

## Okufuna JSON n'okutambula mu mpapula (Pagination)

Teekawo akabonero k'ensi yonna `--json` **nga tonnaba** kussaako kibiina kya biragiro:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ekiragiro ekisooka kisaba ebijjukizo 25 ebisooka; eky'okubiri, 25 ebiddako. Olupapula olumu si kkuumiro lijjuvu. Enfulumya ya JSON ekuuma mannya gonna ag'enjawulo amakulu, ng'ate amateebulo agali ku screen gayinza okugafunza olw'okulaba obulungi.

Okutereka olupapula mu fayiro:

```sh
omi --json memory list --limit 25 --offset 0 > ebijjukizo-lupapula-1.json
```

Enkyusa eno ekola oba eddiza fayiro y'awaka wano. Kakasa nti ekiragiro kiggiddwako bulungi nga tonnakozesa ebirimu. Ensobi ziwandiikibwa mu nfulumya y'ensobi (stderr); fayiro etaliiko kintu si kakwate nti tewali data. Fayiro efulumiziddwa eyinza okubaamu ebikwata ku ggwe: gikuume bulungi mu kyama.

## Okuva mu akawunti (Logout)

```sh
omi auth logout
```

Ekiragiro kino kiggyawo ebisumuluzo ebiterekeddwa wano mu kitundu. Okusazaamu ekisumuluzo ku server, kozesa okufuga ebisumuluzo bya developer mu akawunti yo.

Ebiragiro ebirala n'enkola ez'ekikugu, laba [obulagirizi obukulu obw'Olungereza](../README.md) wamu ne `omi --help`.
