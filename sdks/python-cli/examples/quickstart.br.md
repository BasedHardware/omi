# Kregiñ gant omi-cli

Ar sturlevr-mañ a ziskouez ar c'hentañ urzhioù e brezhoneg. An anvioù urzhioù hag ar c'hemennoù reizhiad a chom e saozneg. Ar skouerioù lenn roet amañ ne gemmont ket ho kounioù, kaozeadennoù, rolloù oberoù pe palioù.

## Staliañ ar programm

Ezhommoù: Python 3.10 pe ur stumm nevesoc'h hag ur gont Omi.

> Evezh: Anv ar pakad war PyPI eo **`omi-cli`**, tra m'eo an urzh lakaet da vont en-dro goude ar staliadur **`omi`**. Ur pakad disheñvel hep liamm anvet `omi` zo war PyPI — na staliit ket ar pakad-se.

Mard eo staliet `pipx`:

```sh
pipx install omi-cli
omi --help
```

A-hend-all, en un endro galloudel Python oberiant:

```sh
python -m pip install omi-cli
omi --help
```

Ma ne gav ket an dermenell `omi`, gwiriit ez eo oberiant an endro galloudel pe emañ kavlec'h `pipx` en ho `PATH`.

## Kennaskañ ho kont

Krogit gant ar skoazeller etregwezhus:

```sh
omi auth login
```

Dibabit kennaskañ dre ar merdeer, pe dibabit an dibarzh evit pegañ un alc'hwez API diorroer Omi. Kuzhat a ra an enankad etregwezhus an alc'hwez; arabat skrivañ an alc'hwez en urzhioù a chomo en istor an dermenell.

Evit kennaskañ war-eeun dre ar merdeer:

```sh
omi auth login --browser
```

Kasit ar c'hennaskañ da benn war an hevelep urzhiataer ma ya an dermenell en-dro, rak d'ur chomlec'h lec'hel e tistro an dilesadur. Heuilhit an titouroù war ar skramm.

Goude-se, gwiriit ar c'hefluniadur hag ar moned API:

```sh
omi auth status
omi auth whoami
```

`status` a ziskouez ar stad lec'hel hag a guzha ar sekredoù, met n'o gwiria ket gant an dafariad. `whoami` a gas ur goulenn dileset; ur berzh a dalvez ez a ho testenioù en-dro reizh.

Enrollet eo ar c'hefluniadur dre ziouer e `~/.omi/config.toml`. Na rannit ket ar restr-mañ rak testenioù personel zo enni.

## Sellout ouzh ho roadennoù

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ur roll goullo a c'hall talvezout traken n'eus ket a elfennoù o klotañ gant ar goulenn. Evit kompren siloù un urzh, sellit ouzh ar skoazell:

```sh
omi memory list --help
omi action-item list --help
```

## Kaout JSON ha furchal er pajennoù

Lakaat an dibarzh hollek `--json` **a-raok** ar strollad urzhioù:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Goulenn a ra an urzh kentañ ar 25 enrolladur kentañ; goulenn a ra an eil an 25 da-heul. Dre se n'eo ket ur bajenn un eilad klok. Mirout a ra an ec'hodad JSON an anaouderioù klok, tra ma c'hall an taolennoù o berraat.

Evit enrollañ ur bajenn en ur restr:

```sh
omi --json memory list --limit 25 --offset 0 > kouniou-pajenn-1.json
```

Krouiñ pe amsaviñ a ra an adsturradur-mañ ur restr lec'hel. A-raok implijout an endalc'had, asurit ez eo aet an urzh da benn vat. Skrivet e vez ar fazioù war stderr; n'eo ket ur restr c'houllo ur brouenn n'eus ket a roadennoù. Titouroù personel a c'hall bezañ er restr: mirit anezhi e surentez.

## Digennaskañ (Log out)

```sh
omi auth logout
```

Dilemel a ra an urzh-mañ an testenioù enrollet ent-lec'hel. Evit dizornout un alc'hwez war an dafariad, implijit mererezh an alc'hwezioù diorroer en ho kont.

Evit urzhioù all hag dibarzhioù araokaet, sellit ouzh ar sturlevr pennañ e saozneg:
[../README.md](../README.md) hag `omi --help`.
