# Snelstartgids omi-cli (Nederlands)

> Praktische gids voor interactie met Omi vanaf de terminal. Geschikt voor zowel mensen als AI-agenten.

`omi-cli` is de officiële command-line interface voor interactie met de developer-API's van [Omi](https://omi.me). Het verwerkt de vier kernbronnen van Omi — **herinneringen, gesprekken, actie-items en doelen** — efficiënt en scriptbaar.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Officiële documentatie:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Broncode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installatie

De aanbevolen installatiemethode is `pipx` voor geïsoleerde afhankelijkheden.

```bash
# Aanbevolen: installeer met pipx
pipx install omi-cli

# Of gebruik pip
pip install omi-cli
```

> **Belangrijk: verschil tussen pakketnaam en commandonaam**
> * Het geïnstalleerde Python-pakket heet **`omi-cli`** (het op zichzelf staande `omi`-pakket is een ander, niet-gerelateerd pakket).
> * Het uitvoerbare commando in de terminal na installatie heet **`omi`**.

Controleer na installatie de versie en help.

```bash
omi --version
omi --help
```

---

## 2. Authenticatie

`omi-cli` ondersteunt twee authenticatiemethoden.

| Methode | Aanbevolen gebruik | Voorbeeldcommando |
| :--- | :--- | :--- |
| **Developer API-sleutel (`omi_dev_*`)** | CI/CD, automatische scripts, AI-agenten | `omi auth login --api-key ...` of omgevingsvariabele |
| **Browser-OAuth (Google/Apple)** | Ontwikkelaars-PC / laptop | `omi auth login --browser` |

### Interactieve aanmelding
Zonder opties wordt u gevraagd om te kiezen tussen aanmelding via de browser of het invoeren van een API-sleutel.

```bash
omi auth login
# 1) Browser — meld aan met uw Google- of Apple-account (voor mensen)
# 2) API-sleutel — plak de developer-sleutel van app.omi.me (voor agenten/CI)
```

### Directe aanmelding via de browser
```bash
omi auth login --browser
```

### De API-sleutel gebruiken
Haal de developer-sleutel op bij **Developer → API Keys** op [app.omi.me](https://app.omi.me) en stel deze in.

```bash
# Via commando instellen
omi auth login --api-key omi_dev_...

# Of via omgevingsvariabele (ideaal voor CI/CD of containers)
export OMI_API_KEY=omi_dev_...
```

### Authenticatiestatus controleren
* `omi auth status`: toont het lokale profiel, het gemaskeerde token en de vervaldatum (werkt offline).
* `omi auth whoami`: stuurt een echt authenticatieverzoek naar de Omi-server (netwerkverbinding vereist).

```bash
omi auth status
omi auth whoami
```

Om af te melden:
```bash
omi auth logout
```

---

## 3. Basisgebruik

U kunt de vier kernbronnen van Omi weergeven en beheren.

### Herinneringen (Memories)
Beheer feiten en kennis die het systeem heeft geleerd.

```bash
# Toon alle herinneringen
omi memory list

# Maak een nieuwe herinnering
omi memory create "Gebruiker geeft de voorkeur aan donkere modus" --category lifestyle

# Toon details van een specifieke herinnering
omi memory get <MEMORY_ID>
```

### Gesprekken (Conversations)
Audio- of tekstgeschiedenis van gesprekken die zijn vastgelegd door het draagbare apparaat of de app.

```bash
# Haal de laatste 5 gesprekken op
omi conversation list --limit 5

# Toon gespreksdetails en transcriptie
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Actie-items (Action Items)
Taken of vervolgitems die automatisch uit gesprekken zijn geëxtraheerd.

```bash
# Toon alleen openstaande actie-items
omi action-item list --open

# Markeer een actie-item als voltooid
omi action-item complete <ACTION_ITEM_ID>
```

### Doelen (Goals)
Beheer doelen waarvan de voortgang wordt bijgehouden.

```bash
# Toon alle doelen
omi goal list
```

---

## 4. Scriptverwerking en JSON-uitvoer (`--json`)

`omi-cli` ondersteunt native JSON-uitvoer. In combinatie met `jq` of Python-scripts moet de **globale optie** `--json` vóór het subcommando worden geplaatst.

```bash
# Herinneringenlijst als JSON ophalen en ID en inhoud extraheren
omi --json memory list | jq '.[] | {id, content, category}'

# Titels van de laatste 5 gesprekken ophalen
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Toon openstaande actie-items
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Toon doelen
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Sessiediagnose

Gebruik deze twee commando'sop in paren voor een snelle probleemoplossing.

```bash
# 1) Controleer eerst de lokale configuratie
omi auth status

# 2) Bevestig met de Omi-server
omi auth whoami

# 3) Start indien nodig de aanmelding opnieuw
omi auth login
```

---

## 6. Beste praktijken

* **Gebruik `--json` in scripts:** Vermijd het parsen van vrije tekst; vertrouw altijd op gestructureerde JSON-uitvoer.
* **Isoleer omgevingen met `pipx`:** Voorkomt afhankelijkheidsconflicten met andere Python-pakketten.
* **Deel geen API-sleutels:** `omi_dev_*`-sleutels verlenen volledige accounttoegang — bewaar ze in een geheimenbeheerder of omgevingsvariabelen.
* **Meld af op gedeelde apparaten:** Gebruik `omi auth logout` na sessies op gedeelde machines.

---

## 7. Probleemoplossing

| Symptoom | Waarschijnlijke oorzaak | Oplossing |
| :--- | :--- | :--- |
| `command not found: omi` | PATH bevat de pipx-bin directory niet | Voer `pipx ensurepath` uit en herstart de terminal |
| `401 Unauthorized` | API-sleutel ongeldig of verlopen | Genereer een nieuwe sleutel op app.omi.me en update |
| `connection refused` | Geen netwerktoegang tot de Omi-server | Controleer internetverbinding en proxy-instellingen |
| `permission denied` op configuratiebestanden | Configuratiedirectory is niet beschrijfbaar | Controleer rechten van `~/.omi/config.toml` |

---

## 8. Snelle links

* Bronrepository: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Volledige documentatie: [docs.omi.me](https://docs.omi.me)
* Issues en ondersteuning: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Discord-community: uitnodiging beschikbaar via de Omi-homepage