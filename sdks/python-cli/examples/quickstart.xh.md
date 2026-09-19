# Amanyathelo Okuqala nge-omi-cli

Esi sikhokelo sicacisa imiyalelo yokuqala ngesiXhosa. Amagama emiyalelo nemiyalezo yenkqubo ahlala engesiNgesi. Imizekelo yemibuzo eboniswe apha ayitshintshi iinkumbulo zakho (memories), iincoko (conversations), imisebenzi emayenziwe (action items), okanye iinjongo (goals).

## Ukufakela inkqubo

Iimfuneko: Python 3.10 okanye inguqulelo entsha kunye ne-akhawunti ye-Omi.

Ukuba une-`pipx` efakiweyo:

```sh
pipx install omi-cli
omi --help
```

Kungenjalo, ungafaka ngaphakathi kwimeko-bume ye-Python esebenzayo (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ukuba i-terminal ayiyifumani i-`omi`, qinisekisa ukuba imeko-bume ebonakalayo iyasebenza okanye ulawulo apho i-`pipx` ibeka khona iifayile zayo ezisebenzayo likwi-`$PATH` yakho.

## Ukudibanisa i-akhawunti yakho

Qala umncedisi osebenzisanayo (interactive assistant):

```sh
omi auth login
```

Khetha ukungena usebenzisa ibrawuza (browser) okanye ukhetho lokuncamathisela isitshixo se-API sikanjiniyela we-Omi. Ukufaka kumncedisi kufihla isitshixo; phepha ukubhala isitshixo kumyalelo oza kuhlala kwimbali ye-terminal.

Ukuya ngqo kwibrawuza:

```sh
omi auth login --browser
```

Ngena kwikhompyuter efanayo naleyo usebenzisa kuyo i-terminal: impendulo yoqinisekiso isebenzisa idilesi yalapha (local address). Landela imiyalelo ekwisikrini.

Emva koko, qinisekisa ubumbeko nokufikelela kwi-API:

```sh
omi auth status
omi auth whoami
```

I-`status` ibonisa imeko yalapha kwaye ifihla imfihlo, kodwa ayiqinisekisi ukuba isebenza njani kwiseva. I-`whoami` yenza isicelo esiqinisekisiweyo; ukuba siphumelele, oko kuqinisekisa ukuba iinkcukacha zisebenza kakuhle ngaphandle kwemfuneko yokubonisa igama lakho.

Ubumbeko bugcinwa njengesiqhelo ku-`~/.omi/config.toml`. Sukwabelana ngale fayile kuba ingaqulatha iinkcukacha zakho eziyimfihlo.

## Ukukhangela idatha yakho

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Uluhlu olungenanto lungathetha nje ukuba akukho zinto zihambelana nombuzo. Sebenzisa uncedo ukufumana izihluzi kumyalelo ngamnye:

```sh
omi memory list --help
omi action-item list --help
```

## Ukufumana i-JSON nokuhamba kumaphepha (Pagination)

Beka ukhetho jikelele `--json` **ngaphambi** kweqela lemiyalelo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Umyalelo wokuqala ucela iinkumbulo zokuqala ezingama-25; owesibini, ezingama-25 ezilandelayo. Iphepha elinye alilona khophi epheleleyo. Imveliso ye-JSON igcina izichazi ngokupheleleyo, ngelixa iitheyibhile ezikwisikrini zinokuzenza mfutshane ukuze zibonakale lula.

Ukugcina iphepha kwifayile:

```sh
omi --json memory list --limit 25 --offset 0 > iinkumbulo-iphepha-1.json
```

Olu tshintsho lwenza okanye lutshintsha ifayile yalapha. Qinisekisa ukuba umyalelo ugqitywe ngempumelelo ngaphambi kokusebenzisa iziqulatho zawo. Iimpazamo zibhalwa kwimveliso yeempazamo (stderr); ifayile engenanto ayisosisiqinisekiso sokuba akukho datha. Ifayile ekhutshelwe ngaphandle ingaqulatha iinkcukacha zobuqu: yigcine ngokukhuselekileyo.

## Ukuphuma kwi-akhawunti (Logout)

```sh
omi auth logout
```

Lo myalelo ususa iinkcukacha ezigcinwe apha ekuhlaleni. Ukurhoxisa isitshixo kwiseva, sebenzisa ulawulo lwezitshixo zonjiniyela kwi-akhawunti yakho.

Kuyo nayiphi na eminye imiyalelo kunye neendlela eziphambili, jonga [isikhokelo esiphambili ngesiNgesi](../README.md) kunye ne-`omi --help`.
