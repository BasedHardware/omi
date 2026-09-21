# Prěnje kroki z omi-cli

Tutón přewodnik wobjasnja prěnje přikazy omi-cli w hornjoserbšćinje. Přikazowe mjena a programowe zdźělenja wostanu w jendźelšćinje. Přikłady w tutón přewodniku waše dopomnjenki, rozmołwy, dźěłowe zapiski abo zaměry njezměnu.

## Instalacija

Trjebaće Python 3.10 abo nowši, a konto Omi.

Jeli `pipx` je hižo instalowany:

```sh
pipx install omi-cli
omi --help
```

Abo móžeće jón do Python virtual environment instalować:

```sh
python -m pip install omi-cli
omi --help
```

Jeli terminal `omi` njenamaka, kontrolujće, hač je virtual environment aktiwny abo hač je `pipx` w `$PATH`.

## Zwjazajće swój konto

Započńće interaktiwny login-wizard:

```sh
omi auth login
```

Móžeće so z browserom přizwolić abo API-kluč wuwiwarja Omi zasadźić. Interaktiwny zapodatk kluč schowa; dajće pozor, zo njewostanje w terminalowej historiji.

Za direktne přizwolenje z browserom:

```sh
omi auth login --browser
```

Přizwołće so na samsnym komputerje, na kotrymž terminal běži: awtorizaciska wotmołwa wužiwa lokalny adresu. Slědujće pokiwy na wobrazowce.

Nětko kontrolujće konfiguraciju a API-kluč:

```sh
omi auth status
omi auth whoami
```

`status` pokazuje lokalny staw a kluč schowa, ale njepřepruwuje na serwerje. `whoami` sćele awtorizowany naprašowanje; jeli so poradźi, potom vaše přistupne daty funguja, ale swoje mjeno njepokazuje.

Konfiguracija je w `~/.omi/config.toml`. Njedźělće so tutón dataju: móže tajne daty wobsahować.

## Wobhladajće daty

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prózdny lisćik móže jenož woznamjenjeć, zo njejsu daty, kotrež so prašenju hodźa. Zo byšće filtry kóždeho přikaza nawuknyli, hlejće pomoc:

```sh
omi memory list --help
omi action-item list --help
```

## JSON a strony

Stajće globalnu opciju `--json` **prjedy** přikazoweje skupiny:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prěni přikaz wróći prěnich 25 dopomnjenkow; druhi wróći přichodnych 25. Jedna strona husto njeje dospołna. JSON pokazuje wšě identifikatory, mjeztymž tabele na wobrazowce je husto skróća.

Za stronu do dataje pisać:

```sh
omi --json memory list --limit 25 --offset 0 > dopomnjenki-strona-1.json
```

Redirect lokalnu dataju wutwori abo pisa na nju. Kontrolujće, hač přikaz je so poradźił, prjedy hač wobsah wužiwaće. Zmylki du na stderr; prózdna dataja njewoznamjenja, zo njejsu daty. Eksportowane dataje móža tajne daty wobsahować: wobchowajće je wěstje.

## Wotzjewjenje

```sh
omi auth logout
```

Tutón přikaz wottwarja lokalne přistupne daty. Zo byšće kluč na serwerje zběhnyli, wužiwajće zrjadowanje wuwiwarskich klučow na swojim konće.

Za dalše přikazy a pokročene opcije hlejće [hłowny jendźelski přewodnik](../README.md) a `omi --help`.
