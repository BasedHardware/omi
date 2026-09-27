# Ar c'hammedoù kentañ gant omi-cli

Al levr-mañ a zispleg ar c'hammedoù (commands) kentañ eus omi-cli e brezhoneg. Chom a ra anvioù ar c'hammedoù hag ar c'hemennadennoù eus ar program e saozneg. Ar skouerioù enklask a weler amañ ne gemmont ket ho memor (memories), ho kaozeadennoù (conversations), ho oberoù (action items) nag ho palioù (goals).

## Staliañ

Rekis: Python 3.10 pe nevesoc'h, hag ur gont Omi.

Mard hoc'h eus `pipx`:

```sh
pipx install omi-cli
omi --help
```

Gallout a rit ivez e staliañ en un endro Python galloudel oberiant:

```sh
python -m pip install omi-cli
omi --help
```

Ma ne gav ket an termen `omi`, bezit sur eo oberiant an endro galloudel pe emañ renkad `pipx` en `$PATH`.

## Liammañ ho kont

Loc'hit ar skoazeller etregwezhel:

```sh
omi auth login
```

Dibabit ar c'hennaskañ dre ar merdeer pe ar pegañ un alc'hwez API diorroer Omi. Kuzhat a ra ar skrivad etregwezhel an alc'hwez; mirout a rit ouzh e skrivañ en ur c'hammed a vefe enrollet e roll istor an termen.

Evit mont war-eeun d'ar merdeer:

```sh
omi auth login --browser
```

Kenniskiñ war an hevelep urzhiataer hag an termen: mont a ra ar respont dilesa d'ar chomlec'h lec'hel. Heuilhit an ditouroù war ar skramm.

Goude-se, gallout a rit gwiriekaat ar c'hefluniadur hag an haeziñ API:

```sh
omi auth status
omi auth whoami
```

Diskouez a ra `status` ar stad lec'hel hag e kuzh ar sekred, met ne wirieka ket talvoudegezh war ar servijer. Gra `whoami` ur goulenn dilesaet; mard a da benn, sklaer eo e talvez an daveennoù-kennaskañ, hep diskouez hoc'h anv.

Enrollañ a ra ar c'hefluniadur dre ziouer en `~/.omi/config.toml`. Na rannit ket ar restr-mañ: gallout a ra bezañ enni daveennoù-kennaskañ prevez.

## Furchal en ho roadennoù

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ul list goullo a dalvez alies ne ra netra kenglotañ gant an enklask. Implijit ar skoazell evit kavout siloù pep kammad:

```sh
omi memory list --help
omi action-item list --help
```

## JSON hag ar pajennaoù

Lakait an dibab hollek `--json` **a-raok** ar strollad kammadoù:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ar c'hammed kentañ a c'houlenn ar 25 memor kentañ; an eil ar 25 war-lerc'h. N'eo ket ur pajenn ur gwir eilad klok. Mirout a ra an ezvonnadur JSON an niveroù klok, tra ma c'hell an taolennoù war ar skramm o berraat.

Evit enrollañ ur bajenn en ur restr:

```sh
omi --json memory list --limit 25 --offset 0 > memor-pajenn-1.json
```

Ar renkell-mañ a grou pe a zistruj ur restr lec'hel. Bezit sur eo echuet ar c'hammed a-raok implijout an endalc'had. Skrivet e vez ar fazioù d'an ezvonnadur fazi (stderr); ur restr c'houllo n'eo ket ur brouadenn n'eus roadenn ebet. Gallout a ra ur restr ezporzhet enderc'hel titouroù personel: dalc'hit anezhi prevez.

## Digennaskañ

```sh
omi auth logout
```

Dilemel a ra ar c'hammed-mañ an daveennoù-kennaskañ enrollet er goudor lec'hel. Evit lakaat un alc'hwez da vezañ didalvoudek war ar servijer, implijit ar merañ alc'hwezioù diorroer en ho kont hoc'h-unan.

Evit muioc'h a gammadoù hag a zibaboù, sellit ouzh [al levr pennañ e saozneg](../README.md) hag `omi --help`.
