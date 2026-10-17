# Snel aan de slag met omi-cli

Deze gids legt de basiscommando's uit in het Nederlands. Commandonamen en
programmaberichten blijven in het Engels. De voorbeeldcommando's hieronder
wijzigen je herinneringen, gesprekken, actie-items of doelen niet.

## Het programma installeren

Vereisten: Python 3.10 of nieuwer en een Omi-account.

Als `pipx` is geïnstalleerd:

```sh
pipx install omi-cli
omi --help
```

Als alternatief installeer je het in een geactiveerde virtuele omgeving:

```sh
python -m pip install omi-cli
omi --help
```

Als de terminal `omi` niet vindt, controleer dan of de virtuele omgeving actief
is of dat de map waarin `pipx` uitvoerbare bestanden plaatst in `PATH` staat.

## Je account koppelen

Start de interactieve gids:

```sh
omi auth login
```

Kies browser-login of plak een Omi developer API-key. De interactieve invoer
verbergt de key; typ hem niet in commando's die in de terminalgeschiedenis
worden bewaard.

Om direct de browser te gebruiken:

```sh
omi auth login --browser
```

Log in op dezelfde computer als de terminal, omdat de authenticatie een lokale
callback gebruikt. Volg de instructies op het scherm.

Controleer na het inloggen de configuratie en API-toegang:

```sh
omi auth status
omi auth whoami
```

`status` toont de lokale toestand en maskeert geheimen, maar controleert niet
of ze op de server geldig zijn. `whoami` doet een geauthenticeerd verzoek; als
dat lukt, werken je credentials zonder je naam te tonen.

De configuratie staat standaard in `~/.omi/config.toml`. Deel dit bestand niet,
want het kan credentials bevatten.

## Je data lezen

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Een lege lijst kan betekenen dat er geen items aan het filter voldoen. Bekijk
de opties per commando via de help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ophalen en pagina's doorlopen

Zet de globale `--json`-optie **vóór** de commandogroep:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Het eerste commando vraagt de eerste 25 herinneringen op; het tweede de
volgende 25. Eén pagina is geen volledige backup. De JSON-uitvoer behoudt de
volledige ID's, terwijl tabellen ID's kunnen inkorten voor de weergave.

Om een pagina naar een bestand te schrijven:

```sh
omi --json memory list --limit 25 --offset 0 > memory-pagina-1.json
```

Deze redirect maakt of overschrijft een lokaal bestand. Controleer dat het
commando succesvol is afgelopen voordat je de inhoud gebruikt. Fouten gaan naar
stderr; een leeg bestand bewijst niet dat er geen data is. Het exportbestand
kan persoonlijke informatie bevatten — houd het privé.

## Profielen gebruiken

De state staat in `~/.omi/config.toml` (te wijzigen via `$OMI_CONFIG`). Elk
profiel heeft een eigen authenticatiemethode en API-adres. Wissel van profiel
met `--profile`:

```sh
omi config profile use werk
omi auth login
omi --profile prive memory list
```

Veelgebruikte configuratiecommando's:

```sh
omi config show
omi config path
omi config profile list
```

## Exit codes

Deze exit codes zijn stabiel en bruikbaar in scripts of agents:

| Code | Betekenis | Voorbeeldsituatie |
| ---: | --- | --- |
| 0 | gelukt | Commando voltooid |
| 1 | gebruiksfout | Verkeerde flag, ontbrekend argument of validatie mislukt |
| 2 | authenticatiefout | Credentials ontbreken, token verlopen of rechten te kort |
| 3 | serverfout | Server 5xx of verbinding mislukt |
| 4 | rate limited | Server gaf HTTP 429 terug |
| 5 | niet gevonden | Server gaf HTTP 404 terug |

## Uitloggen

```sh
omi auth logout
```

Dit verwijdert de lokaal opgeslagen credentials. Om de key op de server in te
trekken, gebruik je het developer-keybeheer van je account.

Voor meer commando's en opties, zie de [Engelse hoofd-README](../README.md) en
voer `omi --help` uit.
