# omi-cli Snelstartgids (Dutch Quickstart)

Praktische naslaggids voor de officiële Omi-opdrachtregelinterface (`omi-cli`).
Dit document behandelt installatie, authenticatie, kernopdrachten voor gegevensbeheer en automatiseringstechnieken voor scripts en autonome agents.

---

## Overzicht en Uitvoerbaar Bestand

* **PyPI-pakketnaam:** `omi-cli`
* **Uitvoerbare opdracht:** `omi`

Om verwarring tijdens installatie en gebruik te voorkomen:

```bash
# Installeren via de pakketnaam:
pipx install omi-cli

# Uitvoeren met het verkorte commando:
omi --help
```

---

## Installatie

Het gebruik van `pipx` wordt aanbevolen om afhankelijkheidsconflicten te vermijden en de CLI in een geïsoleerde virtuele omgeving uit te voeren.

### Aanbevolen Methode (`pipx`)

```bash
pipx install omi-cli
```

Upgraden naar de nieuwste versie:

```bash
pipx upgrade omi-cli
```

### Alternatieve Methode (`pip`)

```bash
pip install --user omi-cli
```

Controleer of de installatie is geslaagd:

```bash
omi --version
```

---

## Authenticatie

De CLI ondersteunt drie primaire authenticatiemethoden: interactief inloggen via de browser, rechtstreekse API-sleutelinvoer en omgevingsvariabelen.

### 1. Interactief Inloggen via Browser

Ideaal voor lokale ontwikkelomgevingen met een grafische interface:

```bash
omi auth login --browser
```

Dit opent een authenticatiepagina in uw webbrowser en bewaart het token veilig op uw lokale systeem.

### 2. Inloggen met API-sleutel (Headless / Geautomatiseerd)

Geschikt voor externe servers, SSH-sessies of CI/CD-pipelines:

```bash
omi auth login --api-key
```

De CLI zal u vragen de API-sleutel in te voeren die is gegenereerd in het Omi-ontwikkelaarsdashboard.

### 3. Omgevingsvariabele

Voor Docker-containers of geautomatiseerde pipelines zonder lokale bestandsopslag:

```bash
export OMI_API_KEY="uw-geheime-api-sleutel"
```

### Authenticatiestatus Controleren

* **Offline controle (lokaal aanwezig token):**
  ```bash
  omi auth status
  ```
* **Online controle (realtime validatie op de server):**
  ```bash
  omi auth whoami
  ```

Lokale sessie beëindigen:

```bash
omi auth logout
```

---

## Primaire Workflows

### Herinneringen (`omi memory`)

Herinneringen zijn atomaire contextitems die door Omi zijn geregistreerd.

```bash
# Recente herinneringen weergeven
omi memory list --limit 10

# Handmatig een nieuwe herinnering toevoegen
omi memory create --text "Projectvergadering gepland voor dinsdag om 10:00 uur met het technische team."

# Semantisch zoeken in herinneringen
omi memory search "projectvergadering"
```

### Gesprekken (`omi conversation`)

Beheer van opgenomen gesprekken en audiotranscripties.

```bash
# Gesprekken weergeven
omi conversation list --limit 5

# Details van een specifiek gesprek ophalen
omi conversation get conv_123456

# Volledig transcript exporteren in Markdown-formaat
omi conversation export conv_123456 --format markdown > transcript.md
```

### Actiepunten en Taken (`omi action-item`)

Taken die automatisch uit gesprekken zijn gedestilleerd.

```bash
# Openstaande actiepunten weergeven
omi action-item list --status pending

# Een actiepunt markeren als voltooid
omi action-item update act_789012 --completed
```

### Doelen (`omi goal`)

Beheer van lange- en kortetermijndoelstellingen.

```bash
# Actieve doelen weergeven
omi goal list

# Nieuw doel aanmaken
omi goal create --title "Meertalige documentatie voltooien" --horizon month

# Voortgang van een doel bijwerken
omi goal update goal_345678 --progress 75
```

---

## Gestructureerde Automatisering (`--json` & `jq`)

Alle `omi`-commando's accepteren de globale `--json`-optie, waardoor de uitvoer direct kan worden verwerkt door scripts en gegevenspijplijnen.

### Gegevens Filteren en Extraheren met `jq`

```bash
# Inhoud van alle herinneringen extraheren
omi --json memory list --limit 20 | jq -r '.[].content'

# Niet-voltooide actiepunten filteren
omi --json action-item list | jq '.[] | select(.completed == false) | {id: .id, description: .description}'
```

---

## Exitcodes Tabel

De CLI hanteert consistente afsluitcodes zodat scripts fouten nauwkeurig kunnen afhandelen:

| Code | Betekenis | Typische Oorzaak |
| :---: | :--- | :--- |
| `0` | **Succes** | Bewerking succesvol voltooid. |
| `1` | **Algemene Fout** | Onverwerkte interne uitzondering of onverwachte storing. |
| `2` | **Argumentfout** | Ongeldige opties, ontbrekende parameters of syntaxisprobleem. |
| `3` | **Niet Geauthenticeerd** | Token ontbreekt, is verlopen of API-sleutel is ongeldig. |
| `4` | **Niet Gevonden** | Gevraagde bron (herinnering, gesprek, doel) bestaat niet. |
| `5` | **Netwerkfout** | Verbindingsstoring of time-out van de server. |

---

## Platformonafhankelijke Scripts

### Bash / Zsh (Linux & macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Omi-authenticatie controleren..."
if ! omi auth status > /dev/null 2>&1; then
    echo "Fout: Authenticatie vereist. Voer 'omi auth login' uit." >&2
    exit 3
fi

echo "Nieuwe notitie opslaan..."
omi memory create --text "Automatische systeemcontrole succesvol voltooid."
```

### PowerShell (Windows)

```powershell
Write-Host "Omi-authenticatie controleren..."
omi auth status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Authenticatie ontbreekt. Voer 'omi auth login' uit."
    exit $LASTEXITCODE
}

Write-Host "Doelen ophalen..."
omi --json goal list | ConvertFrom-Json | ForEach-Object {
    [PSCustomObject]@{
        Id = $_.id
        Titel = $_.title
        Voortgang = "$($_.progress)%"
    }
}
```

---

## Lokale Omi Desktop API-integratie

Wanneer de Omi Desktop-applicatie lokaal actief is, kan de CLI direct communiceren met lokale contextdiensten:

```bash
# Lokale poort configureren
omi local configure --port 8000

# Zoeken in lokaal vastgelegde schermtekst
omi local search-screen "kwartaalrapport"
```

---

## Beheer van Meerdere Profielen

Beheer afzonderlijke omgevingen (zoals privé, werk en test) via de `--profile`-optie of via `~/.omi/config.toml`:

```bash
# Een specifiek profiel gebruiken
omi --profile werk memory list

# Een testprofiel met aangepast API-eindpunt gebruiken
omi --profile staging --api-url https://api-staging.omi.me memory list
```

---

## Beveiliging en Aanbevolen Werkwijzen

1. **Tokengeheimhouding:** Sla tokens of API-sleutels nooit op in openbare versiebeheersystemen.
2. **Geschiedenis van de Shell:** Voorkom het doorgeven van geheimen als directe inline-argumenten op gedeelde systemen; geef de voorkeur aan interactieve invoer of de omgevingsvariabele `OMI_API_KEY`.
3. **Bestandsrechten:** Beperk in Unix-productieomgevingen de toegangsrechten voor de configuratiemap `~/.omi/` (`chmod 700 ~/.omi`).
