# Kom igång med omi-cli

Den här guiden förklarar grundkommandona på svenska. Kommandonamn och
programmeddelanden är på engelska. Exempelkommandona nedan ändrar inte dina
minnen, konversationer, åtgärdsposter eller mål.

## Installera programmet

Krav: Python 3.10 eller senare och ett Omi-konto.

Om `pipx` är installerat:

```sh
pipx install omi-cli
omi --help
```

Alternativt kan du installera i ett aktiverat Python-virtuellt environment:

```sh
python -m pip install omi-cli
omi --help
```

Om terminalen inte hittar `omi`, kontrollera att den virtuella miljön är aktiv
eller att katalogen där `pipx` installerar körbara filer finns i `PATH`.

## Koppla ditt konto

Kör den interaktiva guiden:

```sh
omi auth login
```

Välj inloggning via webbläsare eller klistra in en Omi developer-API-nyckel.
Den interaktiva inmatningen döljer nyckeln — skriv den inte i kommandon som
sparas i terminalhistoriken.

För att använda webbläsaren direkt:

```sh
omi auth login --browser
```

Logga in på samma dator som terminalen eftersom autentiseringen använder en
lokal callback-adress. Följ instruktionerna på skärmen.

Kontrollera efter inloggningen konfigurationen och API-åtkomsten:

```sh
omi auth status
omi auth whoami
```

`status` visar det lokala läget och maskerar hemligheter, men kontrollerar inte
om de är giltiga på servern. `whoami` gör ett autentiserat anrop — lyckas det
fungerar dina uppgifter utan att visa ditt namn.

Konfigurationen sparas som standard i `~/.omi/config.toml`. Dela inte filen —
den kan innehålla inloggningsuppgifter.

## Läs dina data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

En tom lista kan betyda att inget matchade filtret. Se varje kommandos
alternativ via hjälpen:

```sh
omi memory list --help
omi action-item list --help
```

## Hämta JSON och bläddra sidor

Placera den globala flaggan `--json` **före** kommandogruppen:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Det första kommandot hämtar de 25 första minnena, det andra nästa 25. En sida
är ingen fullständig backup. JSON-utdata behåller fullständiga ID:n, medan
tabeller kan korta ID:n för visning.

Spara en sida till en fil:

```sh
omi --json memory list --limit 25 --offset 0 > minnen-sida-1.json
```

Omdirigeringen skapar eller skriver över en lokal fil. Kontrollera att kommandot
slutfördes utan fel innan du använder innehållet. Fel skrivs till stderr; en
tom fil bevisar inte att det saknas data. Exportfilen kan innehålla personlig
information — förvara den privat.

## Använda profiler

Tillståndet lagras i `~/.omi/config.toml` (kan bytas via `$OMI_CONFIG`). Varje
profil har egen autentiseringsmetod och egen API-adress. Byt profil med
`--profile`:

```sh
omi config profile use jobb
omi auth login
omi --profile privat memory list
```

Vanliga konfigurationskommandon:

```sh
omi config show
omi config path
omi config profile list
```

## Slutkoder

Dessa slutkoder är stabila och användbara i skript eller för agenter:

| Kod | Betydelse | Exempel |
| ---: | --- | --- |
| 0 | lyckades | Kommandot slutfördes |
| 1 | användarfel | Fel flagga, saknat argument eller misslyckad validering |
| 2 | autentiseringsfel | Saknade uppgifter, utgången token eller saknade rättigheter |
| 3 | serverfel | Server 5xx eller misslyckad anslutning |
| 4 | rate limited | Servern svarade med HTTP 429 |
| 5 | hittades inte | Servern svarade med HTTP 404 |

## Logga ut

```sh
omi auth logout
```

Tar bort lokalt lagrade uppgifter. För att återkalla nyckeln på servern,
använd developer key-hanteringen i ditt konto.

För fler kommandon och flaggor, se [huvud-README:n på engelska](../README.md)
och kör `omi --help`.
