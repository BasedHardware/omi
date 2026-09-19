# Gutangira Byihuse hamwe na omi-cli

Iki gitabo gisobanura amategeko y'ibanze mu rurimi rw'Ikinyarwanda. Amazina y'amategeko n'ubutumwa bwa porogaramu biguma mu Cyongereza. Ingero z'ibibazo (query) zigaragazwa hano ntizihindura urwibutso rwawe (memories), ibiganiro (conversations), imirimo yo gukora (action items), cyangwa intego (goals).

## Gushyira porogaramu muri mudasobwa (Installation)

Ibisabwa: Python 3.10 cyangwa verisiyo nshya hamwe na konti ya Omi.

Niba ufite `pipx` yashyizwemo:

```sh
pipx install omi-cli
omi --help
```

Ubundi buryo, ushobora kuyishyira muri virtual environment ya Python ikora:

```sh
python -m pip install omi-cli
omi --help
```

Niba mudasobwa (terminal) itabonye `omi`, reba neza niba virtual environment ikora cyangwa niba ububiko bw'amadosiye ya `pipx` buri muri `$PATH` yawe.

## Guhuza konti yawe (Authentication)

Tangiza umufasha w'ikiganiro (interactive assistant):

```sh
omi auth login
```

Hitamo kwinjira ukoresheje mushakisha (browser) cyangwa uburyo bwo gushyiramo urufunguzo rwa developer API ya Omi. Ubu buryo buhisha urufunguzo; wirinde kwandika urufunguzo mu itegeko rishobora kuguma mu mateka ya terminal.

Kugira ngo uhite ujya muri mushakisha:

```sh
omi auth login --browser
```

Injira kuri mudasobwa imwe n'iyo ukoreraho terminal: igisubizo cy'ubwishingizi gikoresha aderesi yo muri mudasobwa (local address). Kurikiza amabwiriza agaragara kuri ecran.

Nyuma yaho, suzuma imiterere no kugera kuri API:

```sh
omi auth status
omi auth whoami
```

`status` yerekana uko ibintu byifashe kuri mudasobwa kandi igahisha amabanga, ariko ntabwo isuzuma ukuri kwayo kuri seriveri. `whoami` yohereza icyifuzo cyemejwe; iyo byagenze neza, byemeza ko imyirondoro ikora neza nta mpamvu yo kugaragaza izina ryawe.

Imiterere isanzwe ibikwa muri `~/.omi/config.toml`. Ntugasangize iyi dosiye abandi kuko ishobora kuba irimo amabanga yawe.

## Gusuzuma amakuru yawe

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Urutonde rutagira kintu rushobora kuba rusobanura ko nta bintu bihuye n'ibyo wasabye. Koresha ubufasha kugira ngo umenye ibishungura kuri buri tegeko:

```sh
omi memory list --help
omi action-item list --help
```

## Kubona JSON no kuzenguruka amapaji (Pagination)

Shyira amahitamo rusange `--json` **mbere** y'itsinda ry'amategeko:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Itegeko rya mbere risaba urwibutso 25 rwa mbere; irya kabiri, 25 rikurikira. Ipaji imwe ntabwo ari kopi yuzuye (backup). Ibisohoka muri JSON bibika ibiranga byose mu buryo bwuzuye, mu gihe imbonerahamwe kuri ecran zishobora kubigabanya kugira ngo bigarapare neza.

Kubika ipaji muri dosiye:

```sh
omi --json memory list --limit 25 --offset 0 > urwibutso-ipaji-1.json
```

Iri yohereza rishya rirema cyangwa rigasimbura dosiye ya mudasobwa. Menya neza ko itegeko ryarangiye neza mbere yo gukoresha ibirimo. Amakosa yandikwa ahabugenewe (stderr); dosiye irimo ubusa ntabwo ari gihamya ko nta makuru ahari. Dosiye yoherejwe ishobora kuba irimo amakuru bwite: yibike ahantu hizewe.

## Gusohoka muri konti (Logout)

```sh
omi auth logout
```

Iri tegeko rikuraho imyirondoro yabitswe muri mudasobwa. Guhagarika urufunguzo kuri seriveri, koresha imicungire y'imfunguzo z'umuterambere muri konti yawe.

Kugira ngo ubone andi mategeko n'amahitamo arenzeho, reba [igitabo cy'amabwiriza y'ibanze mu Cyongereza](../README.md) hamwe na `omi --help`.
