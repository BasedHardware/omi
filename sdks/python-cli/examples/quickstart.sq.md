# Hapat e Parë me omi-cli

Ky udhëzues shpjegon komandat e para në gjuhën shqipe. Emrat e komandave dhe
mesazhet e programit mbeten në anglisht. Shembujt e kërkesave të paraqitura këtu
nuk modifikojnë kujtimet, bisedat, detyrat ose synimet tuaja.

## Instalimi i programit

Kërkesat: Python 3.10 ose një version më i ri dhe një llogari Omi.

Nëse keni të instaluar `pipx`:

```sh
pipx install omi-cli
omi --help
```

Si alternativë, mund ta instaloni brenda një mjedisi virtual të aktivizuar të
Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Nëse terminali nuk e gjen `omi`, kontrolloni që mjedisi virtual të jetë i
aktivizuar ose që direktoria ku `pipx` instalon skedarët e ekzekutueshëm të jetë
në `PATH`-in tuaj.

## Lidhja e llogarisë tuaj

Nisni asistentin ndërveprues (interactive assistant):

```sh
omi auth login
```

Zgjidhni të identifikoheni përmes shfletuesit (browser) ose opsionin për të
ngjitur një çelës API zhvilluesi të Omi. Hyrja ndërvepruese e fsheh çelësin;
shmangni shkrimin e tij në një komandë që do të mbetet në historikun e terminalit.

Për të shkuar drejtpërdrejt në shfletues:

```sh
omi auth login --browser
```

Identifikohuni në të njëjtin kompjuter ku po funksionon terminali: përgjigjja e
autentikimit përdor një adresë lokale. Ndiqni udhëzimet që shfaqen në ekran.

Pas kësaj, verifikoni konfigurimin dhe qasjen në API:

```sh
omi auth status
omi auth whoami
```

`status` tregon gjendjen lokale dhe e fsheh sekretin, por nuk kontrollon vlefshmërinë
në server. `whoami` bën një kërkesë të autentikuar; nëse ka sukses, konfirmon që
kredencialet funksionojnë, pa qenë nevoja të shfaqet patjetër emri juaj.

Konfigurimi ruhet automatikisht në `~/.omi/config.toml`. Mos e ndani këtë skedar:
ai mund të përmbajë kredencialet tuaja konfidenciale.

## Konsultimi i të dhënave tuaja

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Një listë e zbrazët mund të nënkuptojë thjesht se nuk ka elemente që përputhen me
kërkesën. Përdorni ndihmën për të zbuluar filtrat e secilës komandë:

```sh
omi memory list --help
omi action-item list --help
```

## Marrja e JSON dhe lundrimi nëpër faqe

Vendosni opsionin global `--json` **përpara** grupit të komandave:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Komanda e parë kërkon 25 kujtimet e para; e dyta, 25 të tjerat në vazhdim. Një faqe
e vetme pra nuk është një kopje rezervë e plotë (full backup). Dalja JSON ruan
identifikuesit e plotë, ndërsa tabelat në ekran mund t'i shkurtojnë për shfaqje.

Për të ruajtur një faqe në një skedar:

```sh
omi --json memory list --limit 25 --offset 0 > kujtime-faqe-1.json
```

Ky ridrejtim krijon ose zëvendëson skedarin lokal. Verifikoni që komanda ka
përfunduar me sukses përpara se të përdorni përmbajtjen e saj. Gabimet shkruhen në
daljen e gabimeve (stderr); një skedar i zbrazët nuk garanton që nuk ka të dhëna.
Skedari i eksportuar mund të përmbajë të dhëna personale: mbajeni atë privat.

## Dalja nga llogaria (Logout)

```sh
omi auth logout
```

Kjo komandë fshin kredencialet e ruajtura lokalisht. Për të revokuar një çelës në
server, përdorni menaxhimin e çelësave të zhvilluesit në llogarinë tuaj.

Për komandat e tjera dhe opsionet e përparuara, shikoni
[udhëzuesin kryesor në anglisht](../README.md) dhe `omi --help`.
