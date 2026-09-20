# Intambwe z'ibanze za omi-cli

Iki gitabo kigufi gisigura intambwe z'ibanze mu Kirundi (Kirundi). Amazina y'amabwiriza n'ubutumwa bwa porogaramu biguma mu Cungereza. Ingero z'ubushakashatsi ziri hano ntizihindura urwibutso rwawe (memories), ibiyago (conversations), ibikorwa bitegekanijwe (action items), canke imigambi (goals).

## Gushiramwo (Installation)

Ibisabwa: Python 3.10 canke verisiyo nshasha, na konti ya Omi.

Nimba ufise `pipx` yashizwemwo:

```sh
pipx install omi-cli
omi --help
```

Ushobora no kuyishira muri virtual environment ya Python ikora:

```sh
python -m pip install omi-cli
omi --help
```

Nimba porogaramu idabona `omi`, raba neza ko virtual environment ikora canke ko inzira ya `pipx` iri muri `$PATH` yawe.

## Guhuza konti yawe (Connecting your account)

Tangiza uburyo bwo kwinjira:

```sh
omi auth login
```

Hitamwo kwinjira unyuze kuri browser canke gushiramwo urufunguzo rwa API (developer API key) rwa Omi. Uburyo bw'ibazwa buhisha urufunguzo; birinda kurwandika ku mugaragaro mu mateka ya terminal.

Kwinjira ako kanya unyuze kuri browser:

```sh
omi auth login --browser
```

Injira kuri mudasobwa imwe ukoreshamwo terminal: igisubizo c'uburenganzira gikoresha aderesi ya hafi (local address). Kurikiza amabwiriza agaragara kuri ecran.

Hanyuma, suzuma imiterere n'uburenganzira bwa API:

```sh
omi auth status
omi auth whoami
```

`status` yerekana imiterere yo muri mudasobwa ikahisha ibanga, ariko ntiyemeza nimba igikora kuri seriveri. `whoami` ikora ubusabe bwo kwemeza; nimba ikunze, vyemeza ko imyirondoro ikora, bitagombereye kwerekana izina ryawe.

Igenamiterere ribikwa ahasanzwe muri `~/.omi/config.toml`. Ntugasangize iyi dosiye abandi: irimwo amakuru y'ibanga.

## Gushakashatsa amakuru (Data exploration)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Urutonde rurimwo ubusa rushobora gusobanura ko nta bisubizo bihuje n'ivyo ushaka biraboneka. Koresha ubufasha kugira ngo ubone uburyo bwo gushungura buhari kuri buri bwiriza:

```sh
omi memory list --help
omi action-item list --help
```

## Ibisohoka vya JSON no gukwirakwiza amapaji (Pagination)

Shira uburyo bwa `--json` **mbere** y'itsinda ry'amabwiriza:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ibwiriza rya mbere risaba inzibutso 25 za mbere; irya kabiri risaba 25 zikurikira. Ipaji imwe ntabwo ari kopi yose yo kubika. Ibisohoka vya JSON bikomeza indangamuntu zose zuzuye, mu gihe imbonerahamwe zo kuri ecran zishobora kuzigabanya kugira ngo zigaragare neza.

Kubika ipaji muri dosiye:

```sh
omi --json memory list --limit 25 --offset 0 > inzibutso-ipaji-1.json
```

Iki cerekezo co kurungika kirema canke kigasubiriza dosiye yo muri mudasobwa yawe. Raba neza ko ibwiriza ryakozwe neza mbere yo gukoresha ibirimwo. Amakosa yandikwa mu bisohoka vy'amakosa (stderr); dosiye irimwo ubusa ntabwo ari igihamya c'uko nta makuru ahari. Dosiye yarungitswe ishobora kubamwo amakuru yihariye: yirinde kuyereka abandi.

## Gusohoka (Logout)

```sh
omi auth logout
```

Iri bwiriza risiba imyirondoro yabitswe muri mudasobwa yawe. Kugira ngo ukure urufunguzo kuri seriveri, koresha ahashirwa imfunguzo z'abatezimbere muri konti yawe.

Ku yandi mabwiriza n'uburyo bwisumbuye, raba [igitabo nyamukuru c'Icungereza](../README.md) na `omi --help`.
