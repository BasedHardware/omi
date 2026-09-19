# Pehualiztli ica omi-cli

Inin teyacanaliztli quinextia in achto tlanahuatilli ica Nahuatlahtolli. In tlanahuatilli itoca huan in tlahtoltiliztli mocahuah ica Ingles tlahtolli. In tlaixcopinalpan amo quipatlah mopopolhuiliz, mononotzaliz, motequiamatl nozo motlatemoliz.

## Xicmotlalili in tlamachiyotl

Tlen monequi: Python 3.10 nozo yancuic huan ce Omi cuentah.

> Xiquitta: In paquete itoca ipan PyPI ca **`omi-cli`**, ihuan in tlanahuatilli tlen quinextia ca **`omi`**. Onca cececcoc paquete amo tehhuatl itoca `omi` ipan PyPI — amo xictlali inon paquete.

Intla `pipx` tlatlalilli:

```sh
pipx install omi-cli
omi --help
```

Nozo, ipan ce Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Intla in terminal amo quinextia `omi`, xiquitta intla in virtual environment tlatequiltilli nozo in `pipx` amatl ca ipan mo `PATH`.

## Xicsaloni mo cuentah

Xicpehua in tepoztli tepalehuiani:

```sh
omi auth login
```

Xictlapejpeni tequiti ipan navegador, nozo xictlali ce Omi API tlamantli. Inin tlatequiliztli quipatiuh in tlapohualli; amo xiquihcuilo ipan terminal tlahtollotl.

Ic niman calaquiliztli ipan navegador:

```sh
omi auth login --browser
```

Xictlami in calaquiliztli ipan in tepoztlatquitl canin tequiti in terminal, pampa in tlaneltililiztli mocuepa nican. Xictequipano in tlanahuatilli ipan pantalla.

Zatepan, xiquitta in tlachihualiztli huan in API calaquiliztli:

```sh
omi auth status
omi auth whoami
```

`status` quinextia nican tlanahuatilli huan quipatiuh tlatlatilli, tel amo quitta ica in tepozcuitlatl. `whoami` quititlan ce tlatlaniliztli; in cuali nezcayotia mo tlaneltililiztli tequiti cuali.

In tlachihualiztli mocahua ipan `~/.omi/config.toml`. Amo xiquixeuh inin amatl pampa quipia mo tlatlatilamatl.

## Xiquitta mo tlatlaliliz

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ce amatl tlen amo quipia itla hueliz nezcayotia amo onca tlen quitemoa. Ic quimatis in tlanahuatilli, xiquitta in tepalehuiliztli:

```sh
omi memory list --help
omi action-item list --help
```

## Xicseli JSON huan xicpatla in amatl

Xictlali in tlanahuatilli `--json` **achto** in tlanahuatilli ololli:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

In achto tlanahuatilli quitlani 25 tlahcuilolli; in ic ome quitlani occequin 25. Ic inon, ce amatl amo nochi tlacencahualli. JSON quipia nochi tlapohualli, tel in tablas hueli quicotonah.

Ic quipiaz ce amatl ipan ce amatl:

```sh
omi --json memory list --limit 25 --offset 0 > neltiliztli-amatl-1.json
```

Inin tlacuepaliztli quichihua ce nican amatl. Achto xictequilti, xiquitta intla cuali oquiz. In tlatlacolli quiza ipan stderr; ce amatl tlen amo quipia itla amo nezcayotia amo onca tlamantli. Xicmati cuali inin amatl pampa quipia motlamantli.

## Xiquiza (Log out)

```sh
omi auth logout
```

Inin tlanahuatilli quipoloa mo nican tlaneltililiztli. Ic quipoloz ce tlapohualli ipan tepozcuitlatl, xictequilti mo cuentah tlapohualli.

Ic occequin tlanahuatilli huan hueyi tlamantli, xiquitta in achto teyacanaliztli ica Ingles:
[../README.md](../README.md) huan `omi --help`.
