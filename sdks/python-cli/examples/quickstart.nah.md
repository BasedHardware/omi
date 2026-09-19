# Pehualiztli ica omi-cli

Inin tlamachtiliztli quipantlaza in achto tlanahuatilli ica Mexikatlahtolli (Nahuatl).
In tlanahuatiltocaitl ihuan tlatocaitl mochihuazqueh ica Ingles. Inin machiyotl
ahmo quiyancuilia motlalnamiquiliz, tlahtoliztli, tequitl noso tlatitlanilli.

## Tlacencahuiliztli (Instalar)

Tlen monequi: Python 3.10 noso yancuic ihuan ce Omi cuenta.

Tla ticpiya `pipx`:

```sh
pipx install omi-cli
omi --help
```

Noihuan tihueliti titlacencahua ihtic ce yancuic Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Tla terminal ahmo quitta `omi`, xiquitta tla `pipx` noso virtual environment ca ihtic `$PATH`.

## Mocuentatzalan tlasaloliztli

Xicpehualti in tlapalleviliztli:

```sh
omi auth login
```

Xictlahtlani calaquiliztli ica browser noso xicquitzqui in Omi API llave.
In calaquiliztli quiyahuiltia in llave; ahmo xictlahcuilo ipan tlanahuatilli inic ahmo mocahuaz ihtic terminal history.

Inic tiaz niman ic browser:

```sh
omi auth login --browser
```

Xicalaqui ipan cehcentetl tepoztototl canin terminal tequiti. Xictoca in tlanonotzaliztli ipan screen.

Zatepan, xiquitta in tlacencahuiliztli ihuan API calaquiliztli:

```sh
omi auth status
omi auth whoami
```

`status` quitta in tepoztototl tlamantli ihuan quiyahuiltia in ichtacatl. `whoami` quinextia tla in llave cualli tequiti.

Mochintin tlacencahuiliztli ca ipan `~/.omi/config.toml`. Ahmo xicxelo inin amatl pampa quipiya ichtacayotl.

## Xiquitta motlalnamiquiliz dātā

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tla ahtlen ca, quihtoznequi ahmo onca dātā tlen ticnequi. Xictequilti tlapalleviliztli:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ihuan tlaixpanyotl (Pagination)

Xictlali in cemantoc `--json` **achto** in tlanahuatilli:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Achto tlanahuatilli quitlani 25 tlalnamiquiliztli; inic ome quitlani 25 occequimeh. JSON quipiya mochintin ID.

Inic ticpiyaz ce tlaixpanyotl ipan amatl:

```sh
omi --json memory list --limit 25 --offset 0 > tlalnamiquiliztli-1.json
```

Inin amatl hueliti quipiya motlalnamiquiliz ichtacayotl: xicpiya ica tlatolnamiquiliztli.

## Quizahuiliztli (Logout)

```sh
omi auth logout
```

Inin tlanahuatilli quipoloa in llavenimeh ipan motepoztototl. Inic tictlamiltiz in llave ipan server, xicalaqui ipan moxeliuhcayo developer ihtic mocuenta.

Occequintin tlanahuatilli xiquitta ipan [Ingles tlamachtiliztli](../README.md) ihuan `omi --help`.
