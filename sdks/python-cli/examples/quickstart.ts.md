# Nkongomiso wo Hantlisa wa omi-cli

Nkongomiso lowu wu hlamusela swileriso swo sungula hi Xitsonga (Tsonga) swa `omi-cli`. Mavito ya swileriso na marungula ya phurogireme swi tshama swiri hi Xinghezi. Swikombiso swo lavisisa leswi kombisiweke laha a swi cinci miehleketo ya wena (memories), mabulo (conversations), swiendlo leswi faneleke ku endliwa (action items), kumbe swikongomelo swa wena (goals).

## Ku nghenisa phurogireme (Installation)

Swilaveko: Python 3.10 kumbe leyintshwa swinene na akhawunti ya Omi.

Loko u ri na `pipx` leri nghenisiweke:

```sh
pipx install omi-cli
omi --help
```

U nga ha tlhela u yi nghenisa eka ndhawu leyi tirhaka ya Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Loko xileriso xa `omi` xi nga kumiwi eka theminali, tiyisisa leswaku virtual environment ya tirha kumbe ndhawu ya `pipx` yi le ndzeni ka `$PATH` ya wena.

## Ku hlanganisa akhawunti ya wena (Authentication)

Sungula mupfuni wo vulavurisana:

```sh
omi auth login
```

Hlawula ku nghena hi ku tirhisa brawuza (browser) kumbe ku nghenisa Omi developer API key ya wena. Ndlela leyi yi fihla xilotlelo lexi; papalata ku xi tsala eka swileriso leswi nga salaka eka matimu ya theminali.

Ku ya hi ku kongoma eka brawuza:

```sh
omi auth login --browser
```

Nghena eka khomphyuta leyi theminali yi tirhaka eka yona: nhlamulo ya vutiyisisi yi tirhisa adirese ya le kaya. Landzelela swileriso leswi nga eka xikirini.

Endzhaku ka sweswo, tiyisisa ndzulamiso na mfikelelo wa API:

```sh
omi auth status
omi auth whoami
```

`status` yi komba xiyimo xa le kaya naswona yi fihla xihundla, kambe a yi kambeli ku tirha eka sevha (server). `whoami` yi rhumela xikombelo lexi tiyisisiweke; loko swi fambile kahle, yi tiyisa leswaku switifiketi swa tirha handle ko kombisa vito ra wena.

Ndzulamiso hi ntolovelo wu hlayisiwa eka `~/.omi/config.toml`. U nga avelani fayili leyi: yi nga va yi tamele switifiketi swa le xihundleni.

## Ku kambisisa switiviwa swa wena (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Nxaxamelo lowu nga riki na nchumu wu nga ha vula ntsena leswaku a ku na leswi fambisanaka na ndzavisiso. Tirhisa mpfuno ku kuma swihlawulekisi eka xileriso xin'wana na xin'wana:

```sh
omi memory list --help
omi action-item list --help
```

## Ku kuma JSON na ku Avela Matsalwa (Pagination)

Veka xihlawulekisi xa misava xa `--json` **emahlweni** ka ntlawa wa swileriso:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Xileriso xo sungula xi kombela miehleketo yo sungula ya 25; xa vumbirhi xi kombela ya 25 leyi landzelaka. Tluka rin'we a hi nseketelo lowu heleleke (backup). Vuhumelerisi bya JSON byi hlayisa switivisi hinkwaswo, hambileswi tafula ra xikirini ri nga swi komyisaka ku swi komba kahle.

Ku hlayisa tluka eka fayili:

```sh
omi --json memory list --limit 25 --offset 0 > miehleketo-tluka-1.json
```

Ndlela leyi yi vumba kumbe yi siva fayili ya le kaya. Tiyisisa leswaku xileriso xi hetile kahle u nga si tirhisa leswi nga endzeni. Swihoxo swi tsariwa eka vuhumelerisi bya swihoxo (stderr); fayili leyi nga hava nchumu a yi vuli leswaku a ku na switiviwa. Fayili leyi tekiweke yi nga va na rungula ra wena ra le xihundleni: yi hlayise kahle.

## Ku huma eka akhawunti (Logout)

```sh
omi auth logout
```

Xileriso lexi xi susa switifiketi leswi hlayisiweke endhawini ya le kaya. Ku herisa xilotlelo eka sevha, tirhisa vufambisi bya developer key eka akhawunti ya wena.

Kuma swileriso swin'wana na swihlawulekisi swo engetela eka [nkongomiso lowukulu wa Xinghezi](../README.md) na `omi --help`.
