# Pirmieji žingsniai su omi-cli

Šiame vadove paaiškinamos pirmosios komandos lietuvių kalba. Komandų pavadinimai
ir programos pranešimai lieka anglų kalba. Čia pateikti užklausų pavyzdžiai
nekeičia jūsų prisiminimų, pokalbių, užduočių ar tikslų.

## Programos diegimas

Reikalavimai: Python 3.10 arba naujesnė versija ir Omi paskyra.

Jei turite įdiegtą `pipx`:

```sh
pipx install omi-cli
omi --help
```

Kitu atveju galite ją įdiegti aktyvuotoje Python virtualioje aplinkoje:

```sh
python -m pip install omi-cli
omi --help
```

Jei terminalas neranda `omi`, patikrinkite, ar virtuali aplinka yra aktyvuota,
arba ar katalogas, kuriame `pipx` diegia vykdomuosius failus, yra jūsų `PATH`.

## Paskyros prijungimas

Paleiskite interaktyvųjį vedlį:

```sh
omi auth login
```

Pasirinkite prisijungimą per naršyklę arba parinktį įklijuoti Omi kūrėjo API raktą.
Interaktyvus įvedimas paslepia raktą; nerašykite jo komandoje, kuri liks terminalo istorijoje.

Norėdami tiesiogiai atidaryti naršyklę:

```sh
omi auth login --browser
```

Prisijunkite tame pačiame kompiuteryje, kuriame veikia terminalas: autentifikavimo
atsakymas naudoja vietinį adresą. Vykdykite ekrane pateikiamus nurodymus.

Po to patikrinkite konfigūraciją ir prieigą prie API:

```sh
omi auth status
omi auth whoami
```

`status` rodo vietinę būseną ir paslepia paslaptį, bet netikrina galiojimo serveryje.
`whoami` atlieka autentifikuotą užklausą; jei ji sėkminga, patvirtina, kad kredencialai veikia, nebūtinai rodant jūsų vardą.

Konfigūracija pagal numatytuosius nustatymus išsaugoma `~/.omi/config.toml` faile.
Nesidalykite šiuo failu: jame gali būti jūsų konfidencialūs prisijungimo duomenys.

## Duomenų peržiūra

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tuščias sąrašas gali tiesiog reikšti, kad nėra elementų, atitinkančių užklausą.
Naudokite pagalbą, kad sužinotumėte kiekvienos komandos filtrus:

```sh
omi memory list --help
omi action-item list --help
```

## JSON gavimas ir puslapių naršymas

Pateikite visuotinę parinktį `--json` **prieš** komandų grupę:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pirmoji komanda prašo pirmųjų 25 prisiminimų; antroji – kitų 25. Vienas puslapis
nėra visa atsarginė kopija (backup). JSON išvestis išsaugo visus identifikatorius,
o ekrano lentelės gali juos sutrumpinti rodymui.

Norėdami išsaugoti puslapį faile:

```sh
omi --json memory list --limit 25 --offset 0 > prisiminimai-puslapis-1.json
```

Šis peradresavimas sukuria arba pakeičia vietinį failą. Prieš naudodami turinį,
įsitikinkite, kad komanda baigėsi sėkmingai. Klaidos rašomos į klaidų išvestį (stderr);
tuščias failas negarantuoja, kad duomenų nėra. Eksportuotame faile gali būti asmeninės informacijos: laikykite jį privačiai.

## Atsijungimas (Logout)

```sh
omi auth logout
```

Ši komanda ištrina vietoje išsaugotus kredencialus. Norėdami atšaukti raktą serveryje,
naudokite kūrėjo raktų valdymą savo paskyroje.

Kitų komandų ir išplėstinių parinkčių ieškokite [pagrindiniame vadove anglų kalba](../README.md) ir `omi --help`.
