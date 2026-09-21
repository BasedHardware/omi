# Kentañ kammedoù gant omi-cli

Deskrivañ a ra ar stur-hent-mañ ar c'hentañ kammedoù gant omi-cli e brezhoneg. Chom a ra anvioù ar gourc'hemennoù hag an testennoù embannet gant ar goulev e saozneg. Ne gemm ket ar skouerioù er stur-hent-mañ ho soñj, ho kendivizoù, ho elfennoù-ober pe ho palioù.

## Staliañ

Ezhomm a zo eus Python 3.10 pe nevesoc'h, hag eus ur c'hont Omi.

Mard eo dija staliet `pipx`:

```sh
pipx install omi-cli
omi --help
```

Anez, staliit anezhañ en un endro Python galloudus o labourat:

```sh
python -m pip install omi-cli
omi --help
```

Ma ne gav ket an termenadur `omi`, gwiriit hag-eñ eo o labourat an endro galloudus pe hag-eñ emañ kavlec'h pipx en `$PATH`.

## Kennaskañ ho kont

Loc'hit ar sorserenn enskrivañ etregwezhiat:

```sh
omi auth login
```

Gallout a rit en em enskrivañ gant ar merdeer pe lakaat un alc'hwez API diorrenour Omi. Kuzhat a ra an enskrivadenn etregwezhiat hoc'h alc'hwez; bezit war evezh ha na lezit ket anezhañ e roll istor hoc'h termenadur.

Evit en em enskrivañ war-eeun gant ar merdeer:

```sh
omi auth login --browser
```

Enskrivit anezhañ war ar memes urzhiataer ma labour an termenadur warnañ: ar respont aotrouniekaat a implij ur chomlec'h lec'hel. Heuilhit an ditour war ar skramm.

Gwiriit bremañ ar c'hefluniadur hag an alc'hwez API:

```sh
omi auth status
omi auth whoami
```

Diskouez a ra `status` an stad lec'hel hag a guzh ar sekredoù, met ne wiria ket gant ar servijer. Gra a ra `whoami` ur goulenn aotrouniekaet; ma teu a-benn, kadarnaat a ra e labour hoc'h aotrouniekaat, met ne ziskouez ket hoc'h anv.

Emañ ar c'hefluniadur en `~/.omi/config.toml`. Na rannit ket ar restr-mañ: sekredoù enskrivañ a c'hall bezañ enni.

## Furchal roadennoù

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ur roll goullo a c'hall bezañ evit lavaret n'eus roadenn ebet o klotañ gant ar goulenn. Deskit siloù pep gourc'hemenn gant ar skoazell:

```sh
omi memory list --help
omi action-item list --help
```

## Ezvonn JSON ha pajennañ

Lakait an dibarzh hollek `--json` **a-raok** ar strollad gourc'hemennoù:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ar c'hentañ gourc'hemenn a zegemer an 25 soñj kentañ; an eil a zegemer ar 25 da-heul. Alies ne vez ket leun ur bajenn. Miret a ra an ezvonn JSON an holl anaouderien, tra ma vez berrhoet an tablezennoù war ar skramm alies.

Evit skrivañ ur bajenn en ur restr:

```sh
omi --json memory list --limit 25 --offset 0 > soñjoù-pajenn-1.json
```

Krouiñ a ra pe skrivañ a-us d'ur restr lec'hel an adtresadur. Gwiriit hag-eñ eo deuet ar gourc'hemenn a-benn a-raok implij an danvez. Mont a ra ar fazioù da stderr; ur restr goullo ne dalvez ket n'eus roadenn ebet. Restroù ezporzhiet a c'hall bezañ enno titouroù prevez: mirerezh anezho en un doare sur.

## Digennaskañ

```sh
omi auth logout
```

Lamet a ra ar gourc'hemenn-mañ an aotrouniekaat lec'hel miret. Evit freuzañ an alc'hwez war ar servijer, implijit merañ an alc'hwezioù diorrenour war ho kont.

Evit gourc'hemennoù all ha dibarzhioù araokaet, gwelet ar [Stur-hent meur e saozneg](../README.md) hag `omi --help`.
