# Enzimäzet askelit omi-cli:n kel

Tämä opas selvittäy omi-cli:n enzimäzet käskyt (commands) karjalan kielel. Käskyjen nimet da programman viestit oldah anglien kielel. Täs ozutetut ečindykohtazet ei muuteta sinun mustoja (memories), paginoja (conversations), ruadoloja (action items) libo tavoittehii (goals).

## Azendus

Tarvittavat: Python 3.10 libo uudempi, da Omi-tili.

Jos sinul on `pipx`:

```sh
pipx install omi-cli
omi --help
```

Voit azendua sen myös aktiivizeh Python-virtuaaliympäristöh:

```sh
python -m pip install omi-cli
omi --help
```

Jos terminal ei löyvä `omi`, varmista, että virtuaaliympäristö on ruavos libo että `pipx`-kansio on `$PATH`:as.

## Yhtenävyö tili

Ala interaktiivine avustai:

```sh
omi auth login
```

Valiče kirjautuo brauzeran kauti libo liittie Omi developer API -avain. Interaktiivine syöttö peittäy avaimen; vältä kirjuttamastu sidä käskys, kudai jäy terminalanistorijah.

Mennä suorah brauzerah:

```sh
omi auth login --browser
```

Kirjaudu samal tiijonal, kudai terminal käyttäy: autentifikaasivastavus menöy paikallizeh adressih. Nouda ekranal olevia ohjeita.

Sen jälkeh tarkista konfiguratsii da API-pääsy:

```sh
omi auth status
omi auth whoami
```

`status` ozuttau paikallizen tilan da peittäy salaisuon, ga ei tarkista kelpožuutta serveral. `whoami` tegi autentifitun kyzymyksen; jos se ozuttaheskai, on selvä, että tunnukset ruatah, ozuttamatta sinun nimie.

Konfiguratsii on tallendettu oletusarvožesti `~/.omi/config.toml`:ah. Älä jagua tädä failua: sih voi olla peitettyjä tunnuksia.

## Kačo sinun andoi

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tyhjä listu merkiččöy tavalližesti vai sidä, ei nimidä vastua ečindäh. Käytä abuo, löydiäksesi joga käskyn filtrit:

```sh
omi memory list --help
omi action-item list --help
```

## JSON da sivut

Panda globaline opcii `--json` **enne** käskyjoukkua:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Enzimäine käsky kyzyy enzimäzet 25 mustuo; toine kyzyy 25 sit tulijah. Yksi sivu ei ole täydelline kopii. JSON-ulostulo säilyttäy kogonazet luvut, ga taulukot ekranal voijah lyhendiä nidä.

Tallenduakkah sivu failuh:

```sh
omi --json memory list --limit 25 --offset 0 > musto-sivu-1.json
```

Tämä ohjaus luadiy libo kirjuttau piäle paikallizen failun. Varmista, että käsky on loppiettu enne sidä, kon käytät sisäldöä. Hairehet kirjutetaheskai haireh-ulostuloh (stderr); tyhjä failu ei ole tovennus sidä, ei ole andoloi. Eksportoitu failu voi sisältiä personehellistu informatsiedu: pidä sidä peitettyn.

## Lähtö

```sh
omi auth logout
```

Tämä käsky pyhkiy paikallizesti tallendetut tunnukset. Kuin avain serveral ei ruata enämbiä, käytä developer-avaimien haldivondua omas tilis.

Enämbiä käskyjä da opciiloi varte kačo [piäopas anglien kielel](../README.md) da `omi --help`.
