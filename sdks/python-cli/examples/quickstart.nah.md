# Achto tzintiliztli ica omi-cli

Inin temachtilistli quimanextia achto tlanahuatiltin (commands) itech omi-cli ica macehuallahtolli. Itoca tlanahuatiltin ihuan tlahtolli itech programa mocahua ica ingles tlahtolli. Inin tlanexiliztli itech tlatemoliztli tlein monextia nican ahmo quipatla moilnamic (memories), motlahtolilhuitl (conversations), motlatequitiliz (action items) noso motlanahuatil (goals).

## Tlatlaliliztli

Tlein monequi: Python 3.10 noso yancuic, ihuan ce Omi cuentatl.

Intla ticpia `pipx`:

```sh
pipx install omi-cli
omi --help
```

No hueli tictlalia ipan ce Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Intla terminal ahmo quitta `omi`, xicchiuhtica ca virtual environment motequitia noso `pipx` carpeta ca ipan `$PATH`.

## Xicneltilia mocuentatl

Xipehua in palehuiani:

```sh
omi auth login
```

Xicpehpena ica calaqui ipan browser noso xicpachiuica ce Omi developer API llave. In entrax tlein mochiua quitlatia in llave; xicahcicahua ticcuiloa in llave ipan ce tlanahuatilli tlein mopiya ipan terminal historia.

Ica calaqui niman ica browser:

```sh
omi auth login --browser
```

Xicalaqui ipan ce computadora tlein ica terminal: in autenticacion tlanonotzaliztli iauh ipan local dirección. Xictlacamatca in tlanahuatiltin tlein ipan pantalla.

Zatepan, xicchiya in configuración ihuan API calaquiliztli:

```sh
omi auth status
omi auth whoami
```

`status` quinextia in local estado ihuan quitlatia in secret, pero ahmo quichiya in validación ipan servidor. `whoami` quichiua ce autenticado tlatemoliztli; intla mochihua cuali, monextia ca in credenciales motequitia, ahmo quinextia motoca.

In configuración mopiya ica default ipan `~/.omi/config.toml`. Ahmo xictlaxilili inin amatl: hueli quipia privado credenciales.

## Xicitta modata

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ce amatlahcuilolli tlein ahmo quipia tlein quinextia zan ca ahmo oncah tlein quimomachiltia ica tlatemoliztli. Xictlacuiloa in palehuiliztli ica ticahcizque in filtros itech cehcen tlanahuatilli:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ihuan amatlapechtli

Xictlalia in global tlanahuatilli `--json` **achto** itech tlanahuatiltin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

In achto tlanahuatilli quitlatlania in achto 25 memoriame; in ome quitlatlania in occe 25. Ce amatlapechtli ahmo chipahuac copia. In JSON quipiya nochi tlapohualli, pero in tablas ipan pantalla hueli quintzacuiltia.

Ica ticpiyazce ce amatlapechtli ipan ce amatl:

```sh
omi --json memory list --limit 25 --offset 0 > memori-amlapechtli-1.json
```

Inin redirect quichiua noso quicuilonzacuiltia ce local amatl. Xicchiya ca in tlanahuatilli otlamic achto tictequitiz ica in tlein oncah ipan. In errores mocuiloa ipan error output (stderr); ce amatl tlein ahmo quipia tlein ahmo cah prueba ca ahmo oncah data. Ce amatl tlein oquizqui hueli quipia personal información: xicpiya ica privado.

## Quiza

```sh
omi auth logout
```

Inin tlanahuatilli quipoloa in credenciales tlein mopiya ipan local. Ica ticchiuazce ce llave ahmo motequitiz ipan servidor, xictequititz in developer llave ipan mopopol cuentatl.

Ica occequi tlanahuatiltin ihuan tlanahuatiltzintli, xicitta in [principal temachtilistli ipan ingles](../README.md) ihuan `omi --help`.
