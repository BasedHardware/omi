# Aan de slag met omi-cli

Deze handleiding legt de basiscommando's uit in het Nederlands. De namen van de commando's en de programma-uitvoer blijven in het Engels. De zoekvoorbeelden die hier worden getoond, wijzigen of verwijderen geen herinneringen, gesprekken, actiepunten of doelen.

## Het programma installeren

Vereisten: Python 3.10 of nieuwer en een Omi-account.

Als je `pipx` hebt geïnstalleerd:

```sh
pipx install omi-cli
omi --help
```

Als alternatief kun je het installeren binnen een geactiveerde virtuele Python-omgeving:

```sh
python -m pip install omi-cli
omi --help
```

Als de terminal `omi` niet kan vinden, controleer dan of de virtuele omgeving geactiveerd is of dat het installatiepad van `pipx` in je `PATH`-omgevingsvariabele staat.

## Je account koppelen

Start de interactieve inlogwizard:

```sh
omi auth login
```

Kies voor inloggen via de browser of plak een Omi-ontwikkelaars-API-sleutel. De interactieve invoer verbergt de sleutel voor veiligheid; vermijd het typen van sleutels als argumenten die in de terminalgeschiedenis terechtkomen.

Om rechtstreeks naar de browser te gaan:

```sh
omi auth login --browser
```

Log in op dezelfde computer als de terminal: het authenticatieantwoord gebruikt een lokaal adres. Volg de instructies op het scherm.

Controleer daarna de configuratie en de API-toegang:

```sh
omi auth status
omi auth whoami
```

`status` toont de lokale bestandsstatus. `whoami` voert een geauthenticeerd verzoek uit naar de server en bevestigt dat de inloggegevens functioneren.

Standaard wordt de configuratie opgeslagen in `~/.omi/config.toml`. Deel dit bestand niet, omdat het inloggegevens bevat.

## Gegevens opvragen

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Een lege lijst kan eenvoudig betekenen dat er geen items zijn die aan de zoekopdracht voldoen. Gebruik de helpfunctie om de filteropties van elk commando te bekijken:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-uitvoer en paginering

Plaats de algemene vlag `--json` **vóór** de commandogroep:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Het eerste commando haalt de eerste 25 herinneringen op; het tweede haalt de volgende 25 op. Een enkele pagina is geen volledige accountback-up. De JSON-uitvoer behoudt volledige UUID-identificaties.

Om een pagina op te slaan in een bestand:

```sh
omi --json memory list --limit 25 --offset 0 > herinneringen-pagina-1.json
```

Controleer of het commando succesvol is afgerond voordat je het bestand gebruikt. Het geëxporteerde bestand kan persoonlijke gegevens bevatten; bewaar het veilig.

## Uitloggen

```sh
omi auth logout
```

Dit commando verwijdert de lokaal opgeslagen inloggegevens. Om een sleutel op de server in te trekken, gebruik je het sleutelbeheer in je webdashboard.

Zie voor overige commando's en geavanceerde opties de [hoofdhandleiding in het Engels](../README.md) en `omi --help`.
