# Umhlahlandlela Losheshako we-omi-cli

Lomhlahlandlela uchaza imiyalo yekucala ngelulwimi lwesiSwati (Swati) mayelana ne-`omi-cli`. Emagama emiyalo nemilayezo yeluhlelo kuhlala kubhalwe ngesiNgisi. Tibonelo tekuhlola letikhonjiswe lapha atiguculi tikhumbuto takho (memories), tingcoco (conversations), tintfo lokufanele tentiwe (action items), nobe imigomo yakho (goals).

## Kufaka luhlelo (Installation)

Tidzingo: Python 3.10 nobe lensha kakhulu kanye ne-akhawunti ye-Omi.

Nangabe sewunayo i-`pipx`:

```sh
pipx install omi-cli
omi --help
```

Ungaphindze uyifake ngekhatsi kwesimo lesisebentako se-Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Nangabe umyalo we-`omi` ungatfolakali kutheminali, cinisekisa kutsi i-virtual environment iyasebenta nobe kutsi indlela ye-`pipx` isekhatsi kwe-`$PATH` yakho.

## Kuhlanganisa i-akhawunti yakho (Authentication)

Cala umsiti loyincociswano:

```sh
omi auth login
```

Khetsa kungena ngekusebentisa sibhukuzi se-inthanethi (browser) nobe kusebentisa i-Omi developer API key yakho. Lendlela iyafihla lesihluthulelo; gwema kusibhala emiyalweni lengasala emlandvweni wetheminali.

Kute uye ngco kusibhukuzi:

```sh
omi auth login --browser
```

Ngena kukhompyutha lefanako lapho kutheminali isebenta khona: imphendvulo yekucinisekisa isebentisa likheli lasekhaya. Landzela ticondziso letisesikrinini.

Ngemuva kwaloko, cinisekisa kulungiswa nekufinyelela ku-API:

```sh
omi auth status
omi auth whoami
```

I-`status` ikhombisa simo sendzawo futsi ifihla lokuyimfihlo, kodvwa ayihloli kusebenta kwayo kuseva (server). I-`whoami` itfumela sicelo lesicinisekisiwe; uma siphumelele, icinisekisa kutsi tincwadzi tiyasebenta ngaphandle kwekukhombisa ligama lakho.

Kulungiswa kubekwa njengalokuvamile ku-`~/.omi/config.toml`. Ungabelani ngalelifayela: lingahle libe netincwadzi letiyimfihlo.

## Kuhlola idatha yakho (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Luhlu lolungenalutfo lungasho nje kutsi kute lokuhambisana nekusesha. Sebentisa lusito kutfola tihlungi kumyalo ngamunye:

```sh
omi memory list --help
omi action-item list --help
```

## Kutfola i-JSON nekwaba emakhasi (Pagination)

Beka kukhetsa kwasemhlabeni wonkhe kwe-`--json` **ngaphambi** kwelicembu lemiyalo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Umyalo wekucala ucela tikhumbuto tekucala letingu-25; owesibili ucela letingu-25 letilandzelako. Likhasi linye alisilo likhophi leliphelele (backup). Lokuvetwe yi-JSON kugcina tonkhe tinimbali teluphawu, nanobe lithebula lesikrini lingakunciphisa kute kukhonjiswe kahle.

Kugcina likhasi efayeleni:

```sh
omi --json memory list --limit 25 --offset 0 > tikhumbuto-likhasi-1.json
```

Lendlela yakha nobe yenta kabusha lifayela lasendzaweni. Cinisekisa kutsi umyalo uphetfwe kahle ngaphambi kwekusebentisa lokungekhatsi. Emaphutsa abhalwa kumphumela wemaphutsa (stderr); lifayela lelingenalutfo alisho kutsi kute idatha. Lifayela lelikhishiwe lingaba nemininingwane yakho yetimfihlo: ligcine ngekunakekela.

## Kuphuma ku-akhawunti (Logout)

```sh
omi auth logout
```

Lomyalo ususa tincwadzi letibekwe endzaweni yasekhaya. Kute usule sihluthulelo kuseva, sebentisa kuphatfwa kwe-developer key ku-akhawunti yakho.

Kutfola leminye imiyalo netinkhetho letengetiwe, bona [umhlahlandlela lomkhulu wesiNgisi](../README.md) kanye ne-`omi --help`.
