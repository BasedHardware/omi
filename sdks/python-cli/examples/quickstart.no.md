# Kom i gang med omi-cli

Denne veiledningen forklarer de første kommandoene på norsk. Kommandonavn og
programmeldinger forblir på engelsk. Spørreeksemplene som vises her, endrer
ikke dine minner, samtaler, gjøremål eller mål.

## Installere programmet

Krav: Python 3.10 eller nyere og en Omi-konto.

Hvis du har `pipx` installert:

```sh
pipx install omi-cli
omi --help
```

Alternativt kan du installere det i et aktivert virtuelt Python-miljø
(virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Hvis terminalen ikke finner `omi`, må du kontrollere at det virtuelle miljøet
er aktivert, eller at mappen der `pipx` installerer kjørbare filer ligger i din
`PATH`.

## Koble til kontoen din

Start den interaktive veiviseren:

```sh
omi auth login
```

Velg å logge inn via nettleseren eller lim inn en Omi-utvikler API-nøkkel. Den
interaktive inntastingen skjuler nøkkelen; unngå å skrive den i en kommando som
blir lagret i terminalhistorikken.

For å gå direkte til nettleseren:

```sh
omi auth login --browser
```

Logg inn på samme datamaskin som terminalen kjører på: autentiseringsresponsen
bruker en lokal adresse. Følg instruksjonene på skjermen.

Deretter bekrefter du konfigurasjonen og tilgangen til API-et:

```sh
omi auth status
omi auth whoami
```

`status` viser den lokale tilstanden og skjuler hemmeligheten, men sjekker ikke
gyldigheten mot serveren. `whoami` sender en autentisert forespørsel; hvis den
lykkes, bekrefter det at legitimasjonen fungerer, uten nødvendigvis å vise navnet ditt.

Konfigurasjonen lagres som standard i `~/.omi/config.toml`. Ikke del denne
filen: den kan inneholde konfidensiell påloggingsinformasjon.

## Se gjennom dataene dine

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

En tom liste kan ganske enkelt bety at det ikke er noen elementer som matcher
forespørselen. Bruk hjelpen for å oppdage filtre for hver kommando:

```sh
omi memory list --help
omi action-item list --help
```

## Hente JSON og bla gjennom sider

Plasser det globale alternativet `--json` **før** kommandogruppen:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Den første kommandoen ber om de første 25 minnene; den andre, de neste 25. En
enkelt side er derfor ikke en fullstendig sikkerhetskopi (backup). JSON-utdataene
bevarer fulle identifikatorer, mens tabeller på skjermen kan forkorte dem for visning.

For å lagre en side til en fil:

```sh
omi --json memory list --limit 25 --offset 0 > minner-side-1.json
```

Denne omdirigeringen oppretter eller erstatter den lokale filen. Kontroller at
kommandoen ble fullført uten feil før du bruker innholdet. Feil skrives til
feilutdata (stderr); en tom fil garanterer ikke at det ikke finnes data. Den
eksporterte filen kan inneholde personlig informasjon: hold den privat.

## Logge ut (Logout)

```sh
omi auth logout
```

Denne kommandoen sletter lokalt lagret påloggingsinformasjon. For å tilbakekalle
en nøkkel på serveren, bruker du administrasjonen for utviklernøkler på kontoen din.

For resten av kommandoene og avanserte alternativer, se
[hovedveiledningen på engelsk](../README.md) og `omi --help`.
