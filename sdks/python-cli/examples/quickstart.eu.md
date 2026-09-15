# Lehen urratsak omi-cli erabiliz

Gida honek lehen komandoak euskaraz azaltzen ditu. Komandoen izenak eta
programaren mezuak ingelesez mantentzen dira. Hemen agertzen diren kontsulta
adibideek ez dituzte zure oroitzapenak, elkarrizketak, zereginak edo helburuak
aldatzen.

## Programa instalatzea

Baldintzak: Python 3.10 edo berriagoa eta Omi kontu bat.

`pipx` instalatuta baduzu:

```sh
pipx install omi-cli
omi --help
```

Bestela, aktibatutako Python ingurune birtual baten barruan instala dezakezu:

```sh
python -m pip install omi-cli
omi --help
```

Terminalak `omi` aurkitzen ez badu, egiaztatu ingurune birtuala aktibatuta dagoela
edo `pipx`-ek bere exekutagarriak instalatzen dituen direktorioa zure `PATH`
aldagaian dagoela.

## Zure kontua konektatzea

Hasi morroi interaktiboa:

```sh
omi auth login
```

Aukeratu arakatzailean saioa hastea edo Omi garatzailearen API gako bat itsasteko
aukera. Sarrera interaktiboak gakoa ezkutatzen du; saihestu terminalaren
historian geratuko den komando batean idaztea.

Zuzenean arakatzailera joateko:

```sh
omi auth login --browser
```

Hasi saioa terminalaren ordenagailu berean: autentifikazio-erantzunak tokiko
helbide bat erabiltzen du. Jarraitu pantailan agertzen diren argibideak.

Ondoren, egiaztatu konfigurazioa eta APIRako sarbidea:

```sh
omi auth status
omi auth whoami
```

`status`-ek tokiko egoera erakusten du eta sekretua ezkutatzen du, baina ez du
zerbitzarian baliozkotasuna egiaztatzen. `whoami`-k autentifikatutako eskaera bat
egiten du; arrakasta badu, kredentzialek funtzionatzen dutela berresten du, zure
izena zertan erakutsi gabe.

Konfigurazioa lehenespenez `~/.omi/config.toml` fitxategian gordetzen da. Ez partekatu
fitxategi hau: zure kredentzialak izan ditzake.

## Zure datuak kontsultatzea

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Zerrenda huts batek esan nahi izan dezake ez dagoela kontsultarekin bat datorren
elementurik. Erabili laguntza komando bakoitzaren iragazkiak ezagutzeko:

```sh
omi memory list --help
omi action-item list --help
```

## JSON eskuratzea eta orrialdeetan zehar nabigatzea

Jarri `--json` aukera globala komando-multzoaren **aurretik**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lehen komandoak lehenengo 25 oroitzapenak eskatzen ditu; bigarrenak, hurrengo 25ak.
Orrialde bakar bat, beraz, ez da babeskopia osoa. JSON irteerak identifikatzaile
osoak gordetzen ditu; taulek, berriz, bistaratzeko laburtu ditzakete.

Orrialde bat fitxategi batean gordetzeko:

```sh
omi --json memory list --limit 25 --offset 0 > oroitzapenak-1.json
```

Birbideratze honek tokiko fitxategia sortzen edo ordezkatzen du. Egiaztatu
komandoa ondo amaitu dela edukia erabili aurretik. Akatsak errore-irteeran
idazten dira; fitxategi huts batek ez du bermatzen daturik ez dagoenik.
Esportatutako fitxategiak informazio pertsonala izan dezake: mantendu pribatua.

## Saioa amaitzea

```sh
omi auth logout
```

Komando honek lokalean gordetako kredentzialak ezabatzen ditu. Zerbitzarian gako
bat baliogabetzeko, erabili zure kontuko garatzaile-gakoen kudeaketa.

Gainerako komando eta aukera aurreratuetarako, kontsultatu
[gida nagusia ingelesez](../README.md) eta `omi --help`.
