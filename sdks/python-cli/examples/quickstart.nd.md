# Izinyathelo zokuqala nge-omi-cli

Lesi sifundo sihamba ngezinyathelo zokuqala ze-omi-cli ngesiNdebele. Amagama wemiyalo nezaziso zohlelo zihlala ngesiNgisi. Izibonelo kulesi sifundo aziguquli izinkumbulo zakho, izingxoxo, imisebenzi noma imigomo.

## Ukufaka

Udinga i-Python 3.10 noma ngaphezulu, kanye ne-akhawunti ye-Omi.

Uma i-`pipx` isivele ifakiwe:

```sh
pipx install omi-cli
omi --help
```

Noma ungayifaka ku-Python virtual environment esebenzayo:

```sh
python -m pip install omi-cli
omi --help
```

Uma itheminali ingayitholi i-`omi`, hlola ukuthi i-virtual environment iyasebenza noma ukuthi ifolda ye-`pipx` ise-`$PATH`.

## Ukuxhumanisa i-akhawunti yakho

Qala i-wizard yokungena esebenzisanayo:

```sh
omi auth login
```

Ungakhetha ukungena nge-browser noma ukunamathisela ukhi we-API yomthuthukisi we-Omi. Ukufaka okusebenzisanayo kufihla ukhi wakho; qaphela ukuthi ungayivumeli emlandweni wetheminali.

Ukungena ngqo nge-browser:

```sh
omi auth login --browser
```

Ngena kukhompyutha efanayo lapho itheminali isebenza khona: impendulo yokugunyaza isebenzisa ikheli lendawo. Landela imiyalelo esesikrinini.

Manje hlola ukumiswa nokhi we-API:

```sh
omi auth status
omi auth whoami
```

I-`status` ibonisa isimo sendawo futhi ifihla izimfihlo, kodwa ayiqinisekisi kuseva. I-`whoami` yenza isicelo esigunyaziwe; uma siphumelela, siqinisekisa ukuthi amagunya akho ayasebenza, kodwa asibonisi igama lakho.

Ukumiswa kugcinwa ku-`~/.omi/config.toml`. Ungayabelani leli fayela: lingase libe nezimfihlo zokungena.

## Ukuhlola idatha

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Uhlu olungenalutho lungase lisho nje ukuthi akukho datha ehambisana nombuzo. Ukuze ufunde ukusebenzisa umyalo ngamunye, bona usizo:

```sh
omi memory list --help
omi action-item list --help
```

## I-JSON namakhasi

Beka i-option ye-`--json` **ngaphambi** kweqembu lomyalo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Umyalo wokuqala ubuyisela izinkumbulo zokuqala ezingama-25; owesibili ubuyisela ezinye ezingama-25. Ikhasi elilodwa kaningi aligcwaliseki. I-JSON ibonisa zonke izihlonzi, kuyilapho amathebula esikrinini evamise ukuzifinyeza.

Ukwubhala ikhasi efayeleni:

```sh
omi --json memory list --limit 25 --offset 0 > izinkumbulo-ikhasi-1.json
```

I-redirecta yenza ifayela lasendaweni noma isibhalele phezu kwalo. Qinisekisa ukuthi umyalo uphumelele ngaphambi kokusebenzisa okukuyo. Amaphutha aya ku-stderr; ifayela elingenalutho akusho ukuthi akukho datha. Amafayela akhishiwe angase abe nedatha eyimfihlo: wabeke endaweni ephephile.

## Ukuphuma

```sh
omi auth logout
```

Lona umyalo ususa amagunya agciniwe endaweni. Ukukhansela ukhi kuseva, sebenzisa ukuphathwa kokhi yomthuthukisi ku-akhawunti yakho.

Eminye imiyalo namakhethela athuthukile, bona [umhlahlandlela oyinhloko wesiNgisi](../README.md) kanye no-`omi --help`.
