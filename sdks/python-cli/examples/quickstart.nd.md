# Izinyathelo zokuqala nge-omi-cli

Le ncwadi ichaza izinyathelo zokuqala (commands) ze-omi-cli ngesiNdebele. Amagama emiyalo kanye nemilayezo yohlelo ahlala ngesiNgisi. Izibonelo zokusesha ezikhonjiswe lapha aziguquli izinkumbulo zakho (memories), izingxoxo zakho (conversations), imisebenzi yakho (action items) noma imigomo yakho (goals).

## Ukufaka

Okudingekayo: Python 3.10 noma ngaphezulu, kanye ne-akhawunti ye-Omi.

Uma unayo i-`pipx`:

```sh
pipx install omi-cli
omi --help
```

Ungayifaka futhi endaweni ye-Python esebenzayo (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Uma i-terminal ingayitholi i-`omi`, qinisekisa ukuthi indawo esebenzayo iyasebenza noma ukuthi ifolda ye-`pipx` iku-`$PATH`.

## Ukuxhumanisa i-akhawunti yakho

Qala umsizi wokuxhumana:

```sh
omi auth login
```

Khetha ukungena nge-browser noma ukunamathisela ukhiye we-API we-Omi developer. Ukufaka kokuxhumana kufihla ukhiye; gwema ukuwubhala emyalweni ogcina kumlando we-terminal.

Ukuya ngqo ku-browser:

```sh
omi auth login --browser
```

Ngena kukhompyutha efanayo ne-terminal: impendulo yokuqinisekisa iya ekhelini lendawo. Landela imiyalelo esesikrinini.

Ngemva kwalokho, qinisekisa ukuhlelwa kanye nokufinyelela kwe-API:

```sh
omi auth status
omi auth whoami
```

`status` ikhombisa isimo sendawo futhi ifihle imfihlo, kodwa ayiqinisekisi ukusebenza kuseva. `whoami` yenza isicelo esiqinisekisiwe; uma siphumelela, kucaca ukuthi izifakazelo ziyasebenza, ngaphandle kokukhombisa igama lakho.

Ukuhlelwa kugcinwa ngokuzenzakalelayo ku-`~/.omi/config.toml`. Ungayabelani le fayela: ingaqukatha izifakazelo eziyimfihlo.

## Ukuhlola idatha yakho

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Uhlu olungenalutho ngokuvamile lusho nje ukuthi akukho okufana nokusesha. Sebenzisa usizo ukuthola izihlungi zomyalo ngamunye:

```sh
omi memory list --help
omi action-item list --help
```

## JSON namaqembu

Beka inketho yomhlaba `--json` **ngaphambi** kweqembu lomiyalo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Umyalo wokuqala ucela izinkumbulo zokuqala ezingama-25; owesibili ucela ezilandelayo ezingama-25. Ikhasi elilodwa aliyona ikhophi ephelele. I-JSON igcina izinombolo eziphelele, kanti amathebula esesikrinini angazifinyeza.

Ukugcina ikhasi efayeleni:

```sh
omi --json memory list --limit 25 --offset 0 > izinkumbulo-ikhasi-1.json
```

Lokhu kuqondisa kwakha noma kubhala phezu kwefayela lendawo. Qinisekisa ukuthi umyalo usuphothuliwe ngaphambi kokusebenzisa okuqukethwe. Amaphutha abhalwa kokuphumayo kwamaphutha (stderr); ifayela elingenalutho akulona ubufakazi bokuthi ayikho idatha. Ifayela elithunyelwe lingaqukatha ulwazi lomuntu siqu: ligcine liyimfihlo.

## Ukuphuma

```sh
omi auth logout
```

Lo myalo ususa izifakazelo ezigcinwe endaweni. Ukwenza ukhiye ungasebenzi kuseva, sebenzisa ukuphathwa kokhiye we-developer ku-akhawunti yakho.

Ukuze uthole eminye imiyalo nezinketho, bheka [incwadi enkulu ngesiNgisi](../README.md) kanye ne-`omi --help`.
