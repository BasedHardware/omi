# Intambwe ya mbere na omi-cli

Iyi niyoborere yigisha intambwe ya mbere (commands) ya omi-cli mu Kirundi. Amazina y'amategeko n'ubutumwa bw'porogaramu biguma mu Gikinga. Ingero z'ugushakisha zerekanwa ng'aha ntizihindura kwibuka kwawe (memories), ibiganiro vyawe (conversations), ibikorwa vyawe (action items) canke intego zawe (goals).

## Kwishiraho

Ibikenewe: Python 3.10 canke hejuru, na konti Omi.

Niba ufise `pipx`:

```sh
pipx install omi-cli
omi --help
```

Urashobora kandi kuyishira mu karere ka Python virtual gakora:

```sh
python -m pip install omi-cli
omi --help
```

Niba terminal itabona `omi`, ntegereze ko virtual environment ikora canke ko dosiye ya `pipx` iri mu `$PATH`.

## Guhuza konti yawe

Tangira umufasha:

```sh
omi auth login
```

Hitamwo kwinjira mu browser canke kwomeka urufunguzo rwa Omi developer API. Ico winjiza mu buryo bw'ubwenge kirahisha urufunguzo; ntukarwandike mu butegeko buzobikwa mu mateka ya terminal.

Kugira uje kuri browser:

```sh
omi auth login --browser
```

Injira kuri mudasobwa imwe na terminal: inyishu y'ukwemeza ija kuri aderesi y'aho. Kurikiza amabwiriza ari kuri ecran.

Inyuma y'ivyo, genzura iyubakwa n'uko winjira muri API:

```sh
omi auth status
omi auth whoami
```

`status` yerekana uko ibintu biri ng'aho kandi ihisha ibanga, mugabo ntiyigenzura ko ari vyiza kuri server. `whoami` ikora ikibazo cemejwe; niba igenda neza, biragaragara ko ibanga ryawe rikora, uterekanye izina ryawe.

Iyubakwa ribikwa mu buryo busanzwe mu `~/.omi/config.toml`. Ntutangaze iyi dosiye: ishobora kugira amabanga y'umuntu.

## Kuraba amakuru yawe

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Urutonde rw'ubusa akenshi bisobanura gusa ko nta kintu kihuye n'ugushakisha. Koresha ubufasha kugira ubone amashirahamwe ya buri butegeko:

```sh
omi memory list --help
omi action-item list --help
```

## JSON n'imbwebwe

Shira uguhitamwo kw'isi yose `--json` **imbere** y'itsinda ry'amategeko:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Itegeko rya mbere risaba kwibuka 25 kwa mbere; irya kabiri risaba 25 bikurikira. Imbwebwe imwe ntikopi yuzuye. JSON ibika imibare yose, mugabo imbari kuri ecran zishobora kuyigabanya.

Kubika imbwebwe mu dosiye:

```sh
omi --json memory list --limit 25 --offset 0 > kwibuka-imbwebwe-1.json
```

Uku kohereza kurema canke kwandika hejuru ya dosiye y'aho. Ntegereze ko itegeko rirangiye imbere yo gukoresha ibirimwo. Amakosa yandikwa ku gisohoka c'amakosa (stderr); dosiye y'ubusa ntiyerekana ko nta makuru ahari. Dosiye yoherejwe hanze ishobora kugira amakuru y'umuntu: yibike mu ibanga.

## Gusohoka

```sh
omi auth logout
```

Iri tegeko rikuraho amabanga yabitswe aho. Kugira urufunguzo rudakora kuri server, koresha uburongozi bw'urufunguzo rwa developer kuri konti yawe bwite.

Kubona amategeko n'uguhitamwo vyinshi, raba [niyoborere nkuru mu Gikinga](../README.md) na `omi --help`.
