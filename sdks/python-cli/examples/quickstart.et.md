# Esimesed sammud omi-cli abil

See juhend selgitab esimesi käske eesti keeles. Käskude nimed ja programmi
sõnumid jäävad ingliskeelseks. Siin toodud päringunäited ei muuda teie
mälestusi, vestlusi, ülesandeid ega eesmärke.

## Programmi paigaldamine

Nõuded: Python 3.10 või uuem versioon ja Omi konto.

Kui teil on `pipx` paigaldatud:

```sh
pipx install omi-cli
omi --help
```

Teise võimalusena saate selle paigaldada aktiveeritud Pythoni virtuaalkeskkonda
(virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Kui terminal ei leia käsku `omi`, kontrollige, et virtuaalkeskkond oleks
aktiveeritud või et kataloog, kuhu `pipx` käivitatavad failid paigaldab, oleks
teie `PATH` keskkonnamuutujas.

## Oma konto ühendamine

Käivitage interaktiivne abiline:

```sh
omi auth login
```

Valige brauseri kaudu sisselogimine või Omi arendaja API-võtme kleepimise
võimalus. Interaktiivne sisestus peidab võtme; vältige selle kirjutamist
käsusõnasse, mis jääb terminali ajalukku.

Otse brauserisse liikumiseks:

```sh
omi auth login --browser
```

Logige sisse samas arvutis, kus terminal töötab: autentimise vastus kasutab
kohalikku aadressi. Järgige ekraanile ilmuvaid juhiseid.

Pärast seda kontrollige seadistust ja juurdepääsu API-le:

```sh
omi auth status
omi auth whoami
```

`status` näitab kohalikku olekut ja peidab saladuse, kuid ei kontrolli selle
kehtivust serveris. `whoami` teeb autentitud päringu; õnnestumise korral
kinnitab see, et mandaat töötab, ilma et peaks tingimata teie nime kuvama.

Konfiguratsioon salvestatakse vaikimisi asukohta `~/.omi/config.toml`. Ärge
jagage seda faili: see võib sisaldada teie konfidentsiaalseid mandaate.

## Oma andmete vaatamine

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tühi loend võib lihtsalt tähendada, et päringule vastavaid kirjeid pole.
Kasutage abi, et näha iga käsu filtreid:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-i hankimine ja lehekülgedel liikumine

Asetage globaalne valik `--json` käskude grupi **ette**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Esimene käsk küsib esimesed 25 mälestust; teine, järgmised 25. Üks lehekülg
ei ole seega täielik varukoopia (backup). JSON-väljund säilitab täielikud
identifikaatorid, samas kui ekraanitabelid võivad neid kuvamiseks lühendada.

Lehekülje faili salvestamiseks:

```sh
omi --json memory list --limit 25 --offset 0 > malestused-leht-1.json
```

See ümbersuunamine loob või asendab kohaliku faili. Enne sisu kasutamist
veenduge, et käsk lõppes edukalt. Vead kirjutatakse veaväljundisse (stderr);
tühi fail ei garanteeri, et andmeid pole. Eksporditud fail võib sisaldada
isikuandmeid: hoidke see privaatsena.

## Kontolt väljalogimine (Logout)

```sh
omi auth logout
```

See käsk kustutab kohapeal salvestatud mandaadid. Võtme tühistamiseks serveris
kasutage oma konto arendaja võtmete haldust.

Muude käskude ja täpsemate valikute kohta vaadake
[ingliskeelset põhijuhendit](../README.md) ja `omi --help`.
