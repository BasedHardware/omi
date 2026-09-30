# Pirmie soļi ar omi-cli

Šī rokasgrāmata izskaidro pirmās komandas latviešu valodā. Komandu nosaukumi un
programmas ziņojumi paliek angļu valodā. Šeit parādītie vaicājumu piemēri
nemaina jūsu atmiņas, sarunas, uzdevumus vai mērķus.

## Programmas instalēšana

Prasības: Python 3.10 vai jaunāka versija un Omi konts.

Ja jums ir instalēts `pipx`:

```sh
pipx install omi-cli
omi --help
```

Kā alternatīvu to var instalēt aktivizētā Python virtuālajā vidē (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ja terminālis neatrod `omi`, pārbaudiet, vai virtuālā vide ir aktivizēta vai
direktorijs, kurā `pipx` instalē izpildāmos failus, ir iekļauts jūsu `PATH`.

## Sava konta pievienošana

Palaidiet interaktīvo asistentu:

```sh
omi auth login
```

Izvēlieties pieteikties pārlūkprogrammā vai ielīmēt Omi izstrādātāja API atslēgu.
Interaktīvā ievade paslēpj atslēgu; izvairieties no tās rakstīšanas komandā, kas
paliks termināļa vēsturē.

Lai dotos tieši uz pārlūkprogrammu:

```sh
omi auth login --browser
```

Piesakieties tajā pašā datorā, kur darbojas terminālis: autentifikācijas atbilde
izmanto vietējo adresi. Izpildiet ekrānā redzamos norādījumus.

Pēc tam pārbaudiet konfigurāciju un API piekļuvi:

```sh
omi auth status
omi auth whoami
```

`status` parāda vietējo stāvokli un paslēpj noslēpumu, bet nepārbauda tā
derīgumu serverī. `whoami` veic autentificētu pieprasījumu; ja tas ir veiksmīgs,
tas apstiprina, ka akreditācijas dati darbojas, obligāti neparādot jūsu vārdu.

Konfigurācija pēc noklusējuma tiek saglabāta failā `~/.omi/config.toml`.
Nedalieties ar šo failu: tas var saturēt jūsu konfidenciālos akreditācijas datus.

## Savu datu apskate

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tukšs saraksts var vienkārši nozīmēt, ka nav vienumu, kas atbilst vaicājumam.
Izmantojiet palīdzību, lai uzzinātu katras komandas filtrus:

```sh
omi memory list --help
omi action-item list --help
```

## JSON iegūšana un lapu pārlūkošana

Novietojiet globālo opciju `--json` **pirms** komandu grupas:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pirmā komanda pieprasa pirmās 25 atmiņas; otrā — nākamās 25. Viena lapa tādējādi
nav pilnīga rezerves kopija (backup). JSON izvade saglabā pilnos identifikatorus,
kamēr ekrāna tabulas tos var saīsināt parādīšanai.

Lai saglabātu lapu failā:

```sh
omi --json memory list --limit 25 --offset 0 > atminas-lapa-1.json
```

Šī pārvirzīšana izveido vai aizstāj vietējo failu. Pirms satura izmantošanas
pārbaudiet, vai komanda beidzās veiksmīgi. Kļūdas tiek rakstītas kļūdu izvadē
(stderr); tukšs fails negarantē, ka datu nav. Eksportētais fails var saturēt
personisku informāciju: saglabājiet to privātu.

## Izrakstīšanās no konta (Logout)

```sh
omi auth logout
```

Šī komanda dzēš lokāli saglabātos akreditācijas datus. Lai atsauktu atslēgu
serverī, izmantojiet izstrādātāja atslēgu pārvaldību savā kontā.

Citu komandu un papildu opciju aprakstu skatiet
[galvenajā rokasgrāmatā angļu valodā](../README.md) un `omi --help`.
