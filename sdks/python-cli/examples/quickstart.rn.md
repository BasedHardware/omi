# Intangamarara yo gukoresha omi-cli

Iki gitabu gisobanura amategeko ya mbere mu Kirundi (Kirundi). Amazina y'amategeko (commands) n'ubutumwa bwa porogaramu biguma mu Cyongereza. Uturorero twatanzwe hano ntituhindura ivyo wibutse (memories), ibiganiro (conversations), ibikorwa (action items), canke imigabo yawe (goals).

## Gushira porogaramu muri mudasobwa (Kuyinjiza)

Ibikenewe: Python 3.10 canke hejuru yaho, hamwe na konti ya Omi.

Nimba ufise `pipx`:

```sh
pipx install omi-cli
omi --help
```

Canke urashobora kuyinjiza muri Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

## Guhuza konti yawe

Tangiza ubufasha bwa interactive:

```sh
omi auth login
```

Hitamo kwinjira unyuze muri browser canke ushireho urufunguzo rwa Omi developer API.

Kwinjira uciye muri browser ubwaho:

```sh
omi auth login --browser
```

Kugenzura niba bikora no kumenya uko bihagaze:

```sh
omi auth status
omi auth whoami
```

`status` yerekana uko bihagaze aho ukorera, mu gihe `whoami` yemeza niba urufunguzo rwemewe neza na seriveri.

## Kuraba ibiri muri data yawe

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Kugira ubone ubufasha n'amahitamo kuri buri tegeko:

```sh
omi memory list --help
omi action-item list --help
```

## Kuronka JSON no gutembera mu mpapuro (Pagination)

Shira ihitamo rya `--json` **imbere** y'irindi tegeko:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kuzigama impapuro muri dosiye (file):

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

## Gusohoka muri konti (Logout)

```sh
omi auth logout
```

Iri tegeko rikuraho imfunguzo n'amakuru y'injira bibitswe muri mudasobwa.

Ku bindi bisobanuro, raba [igitabu nyamukuru mu Cyongereza](../README.md) na `omi --help`.
