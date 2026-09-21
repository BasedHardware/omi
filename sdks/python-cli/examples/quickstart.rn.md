# Intambwe za mbere na omi-cli

Iyi nkuru igufasha gutangira gukoresha omi-cli, yanditswe mu Kirundi. Amazina y'amategeko n'ubutumwa bw'iyi porogaramu biguma mu Cyongereza. Ingero z'iyi nkuru ntizihindura amakuru yawe, ibiganiro, ibikorwa canke intego zawe.

## Gushiramwo

Ukeneye Python 3.10 canke hejuru yiwe, hamwe na konti ya Omi.

Niba `pipx` isanzweho:

```sh
pipx install omi-cli
omi --help
```

Canke ushobora kuyishiramwo mu karere k'ububiko ka Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Niba terminal idashobora kubona `omi`, genzura ko ikarere k'ububiko kikora canke ko dosiye ya `pipx` iri muri `$PATH`.

## Guhuza konti yawe

Tangiza umufasha wo kwinjira:

```sh
omi auth login
```

Urashobora guhitamwo: kwinjira ukoresheje mucukumbuzi canke ukomeke urufunguzo rwa API rw'umutunganyizi wa Omi. Icyo winjiza mu buryo bwa interineti kirahisha urufunguzo; ube maso nturwire mu mateka ya terminal.

Kwinjira ataco usubiye mu mucukumbuzi:

```sh
omi auth login --browser
```

Injira kuri mudasobwa imwe na terminal: inyishu y'uburenganzira ikoresha aderesi yo mu karere. Kurikiza amabwiriza ari ku igure.

Ubu genzura igenamiterere n'urufunguzo rwa API:

```sh
omi auth status
omi auth whoami
```

`status` yerekana uko ibintu biri mu karere kandi ihisha amabanga, mugabo ntigenzura kuri seriveri. `whoami` irungika ubutumwa bwemewe; niba bigenda neza, urazi ko ibimenyetso vyawe bikora, mugabo ntikwerekana izina ryawe.

Igenamiterere riri muri `~/.omi/config.toml`. Ntukwiragize iyi dosiye: ishobora kuba irimwo amabanga y'ukwinjira.

## Gutohoza amakuru

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Urutonde rudafise kintu rushobora gusa kwerekana ko nta makuru ahuye n'ibyo ushaka. Kugira umenye amafilteri ya buri tegeko, raba ubufasha:

```sh
omi memory list --help
omi action-item list --help
```

## Ibisohoka vya JSON n'ugupanga ku mapeji

Shira uburyo bw'isi yose `--json` **imbere** y'itsinda ry'amategeko:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Itegeko rya mbere rifata amakuru 25 ya mbere; irya kabiri rifata aya kurikira 25. Urupapuro ntirusa n'ikuzuzwe. Ibisohoka vya JSON bigumana indangamuntu zose, mu gihe imbonyi ari kuri ecran zizipfupfusha.

Kwandika urupapuro mu dosiye:

```sh
omi --json memory list --limit 25 --offset 0 > amakuru-urupapuro-1.json
```

Ukohereza aho wateye kurema canke kwandika hejuru ya dosiye yo mu karere. Genzura ko itegeko ryagenze neza imbere y'uko ukoresha ibirimo. Amakosa agenda kuri stderr; dosiye ubusa ntivuga ko nta makuru ariho. Dosiye zoherejwe hanze zishobora kuba zirimwo amabanga: zibike neza.

## Gusohoka

```sh
omi auth logout
```

Iri tegeko rikuraho ibimenyetso vyabitswe mu karere. Kwikuraho urufunguzo kuri seriveri, koresha ubuyobozi bw'urufunguzo rw'umutunganyizi kuri konti yawe.

Ku mategeko menshi n'amahitamwo agezweho, raba [inkuru nyamukuru mu Cyongereza](../README.md) na `omi --help`.
