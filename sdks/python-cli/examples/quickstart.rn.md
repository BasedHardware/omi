# Intambwe z'ibanze za omi-cli

Iki gitabo kigufi gisobanura intambwe z'ibanze mu Kirundi (Kirundi). Amazina y'amabwiriza n'ubutumwa bwa porogaramu biguma mu Cyongereza. Ingero z'ubushakashatsi ziri hano ntizihindura urwibutso rwawe (memories), ibiganiro (conversations), imirimo iteganyijwe (action items), cyangwa intego (goals).

## Gushyiramo (Installation)

Ibisabwa: Python 3.10 cyangwa verisiyo nshya, na konti ya Omi.

Niba ufite `pipx` yashyizwemo:

```sh
pipx install omi-cli
omi --help
```

Ushobora no kuyishyira muri virtual environment ya Python ikora:

```sh
python -m pip install omi-cli
omi --help
```

Niba porogaramu idabona `omi`, reba neza ko virtual environment ikora cyangwa ko inzira ya `pipx` iri muri `$PATH` yawe.

## Guhuza konti yawe (Connecting your account)

Tangiza uburyo bwo kwinjira:

```sh
omi auth login
```

Hitamo kwinjira unyuze kuri browser cyangwa gushyiramo urufunguzo rwa API (developer API key) rwa Omi. Uburyo bw'ibazwa buhisha urufunguzo; birinda kurwandika ku mugaragaro mu mateka ya terminal.

Kwinjira ako kanya unyuze kuri browser:

```sh
omi auth login --browser
```

Injira kuri mudasobwa imwe ukoreshamo terminal: igisubizo cy'uburenganzira gikoresha aderesi ya hafi (local address). Kurikiza amabwiriza agaragara kuri ecran.

Hanyuma, suzuma imiterere n'uburenganzira bwa API:

```sh
omi auth status
omi auth whoami
```

`status` yerekana imiterere yo muri mudasobwa ikahisha ibanga, ariko ntiyemeza niba igikora kuri seriveri. `whoami` ikora ubusabe bwo kwemeza; niba ikunze, byemeza ko imyirondoro ikora, bitagombereye kwerekana izina ryawe.

Igenamiterere ribikwa ahasanzwe muri `~/.omi/config.toml`. Ntugasangize iyi dosiye abandi: irimo amakuru y'ibanga.

## Gushakashatsa amakuru (Data exploration)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Urutonde rurimo ubusa rushobora gusobanura ko nta bisubizo bihuje n'ibyo ushaka biraboneka. Koresha ubufasha kugira ngo ubone uburyo bwo gushungura buhari kuri buri bwiriza:

```sh
omi memory list --help
omi action-item list --help
```

## Ibisohoka bya JSON no gukwirakwiza amapaji (Pagination)

Shyira uburyo bwa `--json` **mbere** y'itsinda ry'amabwiriza:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ibwiriza rya mbere risaba inzibutso 25 za mbere; irya kabiri risaba 25 zikurikira. Ipaji imwe ntabwo ari kopi yose yo kubika. Ibisohoka bya JSON bikomeza indangamuntu zose zuzuye, mu gihe imbonerahamwe zo kuri ecran zishobora kuzigabanya kugira ngo zigaragare neza.

Kubika ipaji muri dosiye:

```sh
omi --json memory list --limit 25 --offset 0 > inzibutso-ipaji-1.json
```

Iki cyerekezo cyo kohereza kirema cyangwa kigasimbuza dosiye yo muri mudasobwa yawe. Reba neza ko ibwiriza ryakozwe neza mbere yo gukoresha ibirimo. Amakosa yandikwa mu bisohoka by'amakosa (stderr); dosiye irimo ubusa ntabwo ari gihamya cy'uko nta makuru ahari. Dosiye yoherejwe ishobora kubamo amakuru yihariye: yirinde kuyereka abandi.

## Gusohoka (Logout)

```sh
omi auth logout
```

Iri bwiriza risiba imyirondoro yabitswe muri mudasobwa yawe. Kugira ngo ukureho urufunguzo kuri seriveri, koresha ahashyirirwa imfunguzo z'abatezimbere muri konti yawe.

Ku yandi mabwiriza n'uburyo bwisumbuyeho, reba [igitabo nyamukuru cy'Icyongereza](../README.md) na `omi --help`.
