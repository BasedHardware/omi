# omi-cli Snelstartgids (Dutch Quickstart)

> Praktische handleiding om rechtstreeks vanuit uw terminal met Omi te communiceren — ontworpen voor ontwikkelaars en autonome AI-agents.

`omi-cli` is de officiële opdrachtregelinterface voor de ontwikkelaars-API van [Omi](https://omi.me). Het stelt u in staat om de vier kernbronnen van het systeem op een gestructureerde en automatiseerbare manier te beheren: herinneringen (memories), gesprekken (conversations), actiepunten (action items) en doelen (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Officiële Documentatie:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Broncode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installatie

Het gebruik van `pipx` wordt aanbevolen om afhankelijkheidsconflicten te vermijden en de CLI in een geïsoleerde virtuele omgeving uit te voeren:

```bash
# Aanbevolen: geïsoleerde installatie met pipx
pipx install omi-cli

# Of via standaard pip
pip install omi-cli
```

> **Let op: Pakketnaam vs. Opdrachtnaam**
> * De pakketnaam op PyPI is **`omi-cli`** (de naam `omi` is een ander, niet-gerelateerd pakket).
> * Het uitvoerbare commando in uw terminal is simpelweg **`omi`**.

Controleer of de installatie is geslaagd met de versie en het helpmenu:

```bash
omi --version
omi --help
```

---

## 2. Authenticatie (Authentication)

`omi-cli` ondersteunt twee primaire authenticatiemethoden:

| Methode | Geschikt voor | Voorbeeldopdracht |
| :--- | :--- | :--- |
| **API-sleutel (`omi_dev_*`)** | Automatiseringen, CI/CD, headless servers, AI-agents | `omi auth login --api-key ...` of `OMI_API_KEY` |
| **Browser OAuth (Google/Apple)** | Lokale workstations en ontwikkelaars | `omi auth login --browser` (Google) / `--provider apple` |

### Interactief Inloggen
Wanneer uitgevoerd zonder extra argumenten, vraagt de wizard welke methode u wilt gebruiken:

```bash
omi auth login
# 1) Browser — Inloggen via Google in de webbrowser (gebruik `--provider apple` voor Apple)
# 2) API key — Plak uw API-sleutel gegenereerd op app.omi.me
```

### Direct Inloggen via Browser
```bash
# Standaard inloggen via Google
omi auth login --browser

# Alternatief via Apple
omi auth login --browser --provider apple
```

### Gebruik van een Ontwikkelaars-API-sleutel
Genereer uw sleutel in het [app.omi.me](https://app.omi.me)-dashboard onder **Developer → API Keys**:

```bash
# Opslaan in het lokale profiel via de opdrachtregel
omi auth login --api-key omi_dev_...

# Of instellen als omgevingsvariabele (ideaal voor containers en CI/CD)
# Let op: als het lokale profiel al een opgeslagen sleutel heeft, voer dan eerst `omi auth logout` uit.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### Authenticatiestatus Controleren
* `omi auth status`: Toont het actieve lokale profiel en de gemaskeerde sleutel; de vervaldatum wordt alleen weergegeven voor OAuth-profielen (werkt offline).
* `omi auth whoami`: Stuurt een verificatieverzoek naar de Omi-server om de geldigheid in realtime te bevestigen (vereist netwerkverbinding).

```bash
omi auth status
omi auth whoami
```

Sessie beëindigen:
```bash
omi auth logout
# Als OMI_API_KEY in de omgeving is ingesteld, verwijder deze dan ook uit de sessie (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Primaire Commando's

### Herinneringen (Memories)
Contextuele feiten en notities vastgelegd door Omi:

```bash
# Opgeslagen herinneringen weergeven
omi memory list

# Nieuwe herinnering aanmaken
omi memory create "Geeft de voorkeur aan beknopte technische antwoorden met Python-voorbeelden" --category work

# Details van een specifieke herinnering ophalen
omi memory get <MEMORY_ID>
```

### Gesprekken (Conversations)
Audio-opnamen en teksttranscripties vastgelegd door Omi-apparaten:

```bash
# De 5 meest recente gesprekken weergeven
omi conversation list --limit 5

# Gespreksdetails en volledige teksttranscriptie ophalen
omi conversation get <CONVERSATION_ID> --include-transcript

# Volledige transcriptie exporteren naar een JSON-bestand
omi --json conversation get <CONVERSATION_ID> --include-transcript > transcriptie.json
```

### Actiepunten en Taken (Action Items)
Taken die automatisch uit gesprekken zijn gedestilleerd:

```bash
# Openstaande actiepunten weergeven
omi action-item list --open

# Een taak voltooien
omi action-item complete <ACTION_ITEM_ID>
```

### Doelen (Goals)
Voortgangsstatistieken en langetermijndoelen:

```bash
# Actieve doelen weergeven
omi goal list

# Nieuw kwantitatief doel aanmaken
omi goal create "Drink dagelijks 2L water" --type numeric --target 2 --unit liters
```

---

## 4. Gestructureerde Automatisering en JSON-uitvoer (`--json`)

`omi-cli` biedt eersteklas ondersteuning voor datapijplijnen. Door de globale optie `--json` mee te geven, wordt uitvoer als geldige JSON geretourneerd:

```bash
# Herinneringen in JSON weergeven en velden extraheren met jq
omi --json memory list | jq '.[] | {id, content, category}'

# Titels van recente gesprekken extraheren
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Openstaande taken als ruwe JSON bekijken
omi --json action-item list --open | jq '.'
```

> **Belangrijke Syntaxisregel:**
> `--json` is een **globale optie** en moet **voor** het subcommando worden geplaatst:
> * Juist: `omi --json memory list`
> * Onjuist: `omi memory list --json`

---

## 5. Afsluitcodes (Exit Codes)

Betrouwbare foutafhandeling voor shellscripts en CI/CD-pipelines:

| Exitcode | Betekenis | Beschrijving |
| :---: | :--- | :--- |
| `0` | **Succes (Success)** | Bewerking succesvol voltooid. |
| `1` | **Gebruiksfout (Validatiefout)** | Ongeldige gegevenswaarden of applicatievalidatiefout; Click-parsersyntaxfouten retourneren code `2`. |
| `2` | **Authenticatiefout / CLI-syntaxis** | Niet geauthenticeerd, verlopen token of ongeldige Click-parseropties. |
| `3` | **Server- / Netwerkfout (Server Error)** | HTTP 5xx-respons, time-out of server onbereikbaar. |
| `4` | **Snelheidslimiet (Rate Limited)** | HTTP 429-respons — verzoek geblokkeerd door rate limit. |
| `5` | **Niet Gevonden (Not Found)** | HTTP 404-respons — opgevraagde bron bestaat niet. |

---

## 6. Voorbeelden per Shell-omgeving

### Bash / Zsh (Linux / macOS)
```bash
# API-sleutel instellen in sessie
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Commando uitvoeren en afsluitcode controleren
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Fout bij het ophalen van gebruikersherinneringen." >&2
fi
```

### PowerShell (Windows)
```powershell
# Omgevingsvariabele instellen in PowerShell
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# JSON-uitvoer direct converteren naar PowerShell-objecten
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Foutcontrole via $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi-opdracht mislukt met code $LASTEXITCODE"
}
```

---

## 7. Lokale Desktop API-integratie

Wanneer de Omi Desktop-toepassing actief is op uw computer, kan de CLI lokale schermgegevens opvragen zonder cloud-aanroepen:

```bash
# Lokaal eindpunt configureren (omgevingsvariabele aanbevolen om token te beschermen)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Lokale verbindingsstatus controleren
omi --json local status

# Zoeken in recente visuele tijdlijn
omi --json local search-screen "Kwartaalrapport" --days 7 --app Safari
```

---

## 8. Beheer van Meerdere Profielen (Profiles)

Schakel tussen persoonlijke accounts, werkaccounts of testomgevingen met de optie `--profile`. Instellingen worden opgeslagen in `~/.omi/config.toml`:

```bash
# Persoonlijk profiel aanmaken en inloggen
omi --profile personal auth login

# Werkprofiel aanmaken en inloggen
omi --profile work auth login

# Commando's uitvoeren met een specifiek profiel
omi --profile work memory list

# Testprofiel uitvoeren met aangepast eindpunt
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## 9. Aanbevolen Veiligheidsmaatregelen

* **Geen sleutels in Git:** Commit nooit API-sleutels naar publieke versiebeheersystemen; gebruik secret managers of `.env`-bestanden in `.gitignore`.
* **Shell-geschiedenis:** Vermijd het rechtstreeks doorgeven van sleutels als argumenten; geef de voorkeur aan interactieve invoer of `OMI_API_KEY`.
* **Maprechten:** Beperk op Unix-systemen de toegangsrechten voor de map `~/.omi/` (`chmod 700 ~/.omi`).
