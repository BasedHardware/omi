# Fyrstu skref með omi-cli

Þessi handbók útskýrir fyrstu skipanirnar á íslensku. Nöfn skipana og skilaboð
forritsins eru áfram á ensku. Fyrirspurnadæmin sem hér birtast breyta ekki
minningum þínum, samtölum, verkefnum eða markmiðum.

## Uppsetning forritsins

Kröfur: Python 3.10 eða nýrri útgáfa og Omi aðgangur.

Ef þú ert með `pipx` uppsett:

```sh
pipx install omi-cli
omi --help
```

Einnig er hægt að setja það upp í virku sýndarumhverfi (virtual environment)
í Python:

```sh
python -m pip install omi-cli
omi --help
```

Ef skipanalínan (terminal) finnur ekki `omi`, gakktu úr skugga um að sýndarumhverfið
sé virkt eða að mappan þar sem `pipx` setur keyrsluskrár sé í `PATH` breytunni þinni.

## Tengdu aðganginn þinn

Ræstu gagnvirka aðstoðarmanninn:

```sh
omi auth login
```

Veldu að skrá þig inn í gegnum vafra eða límdu inn Omi forritara API lykil.
Gagnvirka innslátturinn felur lykilinn; forðastu að skrifa hann í skipun sem
verður eftir í sögu skipanalínunnar.

Til að fara beint í vafrann:

```sh
omi auth login --browser
```

Skráðu þig inn á sömu tölvu og skipanalínan keyrir á: auðkenningarsvarið notar
staðbundið vistfang. Fylgdu leiðbeiningunum á skjánum.

Eftir það skaltu staðfesta uppsetningu og aðgang að API:

```sh
omi auth status
omi auth whoami
```

`status` sýnir staðbundna stöðu og felur leyndarmálið en athugar ekki gildi á
netþjóninum. `whoami` sendir auðkennda beiðni; ef hún tekst staðfestir hún að
aðgangsorðin virki, án þess endilega að sýna nafnið þitt.

Stillingarnar eru sjálfgefið vistaðar í `~/.omi/config.toml`. Ekki deila þessari
skrá: hún gæti innihaldið leynilegu aðgangsupplýsingarnar þínar.

## Skoðaðu gögnin þín

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tómur listi gæti einfaldlega þýtt að engir hlutir passi við fyrirspurnina.
Notaðu hjálpina til að sjá síur fyrir hverja skipun:

```sh
omi memory list --help
omi action-item list --help
```

## Sækja JSON og fletta á milli síðna

Settu altæka valkostinn `--json` **fyrir framan** skipanahópinn:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Fyrri skipunin biður um fyrstu 25 minningarnar; sú seinni um næstu 25. Ein síða
er því ekki fullkomið öryggisafrit (backup). JSON úttakið heldur fullum auðkennum,
á meðan töflur á skjánum gætu stytt þau til sýnis.

Til að vista síðu í skrá:

```sh
omi --json memory list --limit 25 --offset 0 > minningar-sida-1.json
```

Þessi endurbeining býr til eða skrifar yfir staðbundnu skrána. Athugaðu að skipunin
hafi klárast án villna áður en innihaldið er notað. Villur eru skrifaðar í
villuúttak (stderr); tóm skrá tryggir ekki að engin gögn séu til staðar. Útflutta
skráin getur innihaldið persónuupplýsingar: hafðu hana persónulega.

## Útskráning (Logout)

```sh
omi auth logout
```

Þessi skipun eyðir staðbundið vistuðum aðgangsupplýsingum. Til að afturkalla lykil
á netþjóninum skal nota stjórnun forritaralykla á aðganginum þínum.

Fyrir aðrar skipanir og ítarlegri valkosti, sjá
[aðalhandbókina á ensku](../README.md) og `omi --help`.
