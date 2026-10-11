# Izinyathelo Zokuqala nge-omi-cli

Lo mhlahlandlela uchaza imiyalo yokuqala ngesiZulu. Amagama emiyalo nemilayezo
yohlelo kuhlala kungesiNgisi. Izibonelo zemibuzo ezivela lapha aziguquleli
izinkumbulo zakho, izingxoxo, imisebenzi noma imigomo yakho.

## Ukufaka uhlelo

Izidingo: Python 3.10 noma inguqulo entsha kanye ne-akhawunti ye-Omi.

Uma une-`pipx` efakiwe:

```sh
pipx install omi-cli
omi --help
```

Kungenjalo, ungafaka ngaphakathi kwendawo ebonakalayo ye-Python esebenzayo
(activated virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Uma i-terminal ingayitholi i-`omi`, hlola ukuthi indawo ebonakalayo iyasebenza
noma ukuthi umkhombandlela lapho i-`pipx` ifaka khona amafayela ayo asetshenziswayo
uku-`PATH` yakho.

## Ukuxhuma i-akhawunti yakho

Qala umsizi osebenzisanayo (interactive assistant):

```sh
omi auth login
```

Khetha ukungena ngemvume kusiphequluli (browser) noma inketho yokunamathisela
ukhiye we-API kanjiniyela (developer API key) we-Omi. Ukufaka okusebenzisanayo
kufihla ukhiye; gwema ukuwubhala emyalweni ozosala emlandweni we-terminal.

Ukuya ngqo kusiphequluli:

```sh
omi auth login --browser
```

Ngena ngemvume kukhompyutha efanayo ne-terminal: impendulo yokuqinisekisa
isebenzisa ikheli lendawo (local address). Landela imiyalelo evela esikrinini.

Ngemuva kwalokho, qinisekisa ukucushwa nokufinyelela ku-API:

```sh
omi auth status
omi auth whoami
```

I-`status` ibonisa isimo sendawo futhi ifihla imfihlo, kodwa ayihloli ukufaneleka
kuseva. I-`whoami` yenza isicelo esiqinisekisiwe; uma iphumelela, iqinisekisa
ukuthi izifakazelo ziyasebenza, ngaphandle kokubonisa igama lakho nakanjani.

Ukucushwa kugcinwa ngokuzenzakalelayo kokuthi `~/.omi/config.toml`. Ungabelani
ngaleli fayela: lingaqukatha izifakazelo zakho eziyimfihlo.

## Ukubheka idatha yakho

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Uhlu olungenalutho lungasho ukuthi azikho izinto ezihambisana nombuzo. Sebenzisa
usizo ukuze uthole izihlungi zomyalo ngamunye:

```sh
omi memory list --help
omi action-item list --help
```

## Ukuthola i-JSON nokuzulazula emakhasini

Beka inketho yomhlaba jikelele `--json` **ngaphambi** kweqembu lomyalo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Umyalo wokuqala ucela izinkumbulo zokuqala ezingu-25; owesibili, ezingama-25
ezilandelayo. Ikhasi elilodwa alilona ikhophi yesipele ephelele. Okukhiphayo
kwe-JSON kugcina izihlonzi ezigcwele, kuyilapho amathebula engawafingqa ukuze
aboniswe.

Ukugcina ikhasi efayeleni:

```sh
omi --json memory list --limit 25 --offset 0 > izinkumbulo-ikhasi-1.json
```

Lokhu kuqondisa kabusha kudala noma kungene esikhundleni sefayela lendawo.
Qinisekisa ukuthi umyalo uqede ngempumelelo ngaphambi kokusebenzisa okuqukethwe
kuwo. Amaphutha abhalwa kokukhiphayo kwephutha (stderr); ifayela elingenalutho
aliqinisekisi ukuthi ayikho idatha. Ifayela elithunyelwe lingaqukatha imininingwane
yomuntu siqu: ligcine liyimfihlo.

## Ukuphuma ngemvume (Logout)

```sh
omi auth logout
```

Lo myalo ususa izifakazelo ezigcinwe endaweni. Ukuhoxisa ukhiye kuseva, sebenzisa
ukuphathwa kokhiye kanjiniyela ku-akhawunti yakho.

Ngeminye imiyalo nezinketho ezithuthukile, bheka
[umhlahlandlela oyinhloko ngesiNgisi](../README.md) kanye ne-`omi --help`.
