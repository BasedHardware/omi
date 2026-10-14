# omi-cli — Nederlandse snelstartgids

> Een praktische gids om met Omi vanuit de terminal te werken. Geschikt voor mensen én voor AI-agenten.

`omi-cli` is de officiële opdrachtregel-client voor de [Omi](https://omi.me) ontwikkelaars-API.
Het biedt snelle en scriptbare toegang tot de vier kernentiteiten van Omi:
herinneringen, gesprekken, actie-items en doelen.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentatie:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Broncode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installatie

De aanbevolen methode is `pipx`: het installeert het hulpmiddel in een geïsoleerde
omgeving, zodat de afhankelijkheden niet botsen met uw projecten.

```bash
# aanbevolen: installeren met pipx
pipx install omi-cli

# of met pip
pip install omi-cli
```

> **Belangrijk: de pakketnaam en de commandonaam verschillen.**
> * Het geïnstalleerde pakket is **`omi-cli`** (het afzonderlijke pakket `omi` is een ander, niet-gerelateerd project).
> * Na installatie voert u het commando **`omi`** uit.

Controleer dat alles werkt:

```bash
omi --version
omi --help
```

---

## 2. Authenticatie

`omi-cli` ondersteunt twee inlogmethoden.

| Methode | Geschikt voor | Commando |
| :--- | :--- | :--- |
| **Ontwikkelaarssleutel (`omi_dev_*`)** | CI/CD, scripts, AI-agenten | `omi auth login --api-key ...` of omgevingsvariabele |
| **Browser-login (Google/Apple)** | Werk op uw eigen computer | `omi auth login --browser` |

### Interactief inloggen

Voer uit zonder opties en het vraagt welke methode u wilt gebruiken.

```bash
omi auth login
# 1) Browser — inloggen met Google of Apple (voor mensen)
# 2) API key — plak een ontwikkelaarssleutel van app.omi.me (voor agenten/CI)
```

Kiest u de sleutel, dan wordt de invoer verborgen zodat de sleutel niet in de
terminalgeschiedenis terechtkomt.

### Direct inloggen via de browser

```bash
omi auth login --browser
```

### Inloggen met een ontwikkelaarssleutel

Haal de sleutel op [app.omi.me](https://app.omi.me) onder **Developer → API Keys**.

```bash
# sla de sleutel op in de configuratie
omi auth login --api-key omi_dev_...

# of geef hem door via de omgeving — beter voor CI/CD en containers
export OMI_API_KEY=omi_dev_...
```

De omgevingsvariabele `OMI_API_KEY` wordt gebruikt wanneer er geen sleutel is
opgeslagen in het actieve profiel, dus in een container hoeft niets naar schijf
geschreven te worden. Als het profil al een sleutel heeft, gaat die voor op de
omgevingsvariabele.

### Controleer de toegang

Twee commando's beantwoorden verschillende vragen en mogen niet verward worden:

* `omi auth status` — wat **lokaal** is opgeslagen: profiel, gemaskeerde sleutel, vervaldatum.
  Werkt zonder netwerk.
* `omi auth whoami` — een verzoek **aan de Omi-server**: verifieert dat de sleutel echt wordt geaccepteerd.
  Vereist netwerk.

```bash
omi auth status    # lokale controle, offline
omi auth whoami    # controle op de server
```

Vernieuw een bijna-verlopen token zonder opnieuw in te loggen — dit commando geldt
**alleen voor browser/OAuth-sessies**. Voor een profil dat met een API-sleutel
(`omi_dev_*`) is geauthenticeerd, faalt `omi auth refresh` met een gebruiksfout
(code 1): er is geen token om te vernieuwen — wijzig de sleutel in de Omi-webapp
indien nodig:

```bash
omi auth refresh
```

Uitloggen:

```bash
omi auth logout
```

---

## 3. Basiscommando's

### Herinneringen (memories)

Feiten en kennis die het systeem over u heeft onthouden.

```bash
# lijst van herinneringen
omi memory list

# maak er een nieuwe
omi memory create "De gebruiker geeft de voorkeur aan het donkere thema" --category lifestyle

# bekijk een specifieke
omi memory get <MEMORY_ID>
```

### Gesprekken (conversations)

Stem- en tekstgeschiedenis van het apparaat of de app.

```bash
# de 5 meest recente gesprekken
omi conversation list --limit 5

# een volledig gesprek met transcript
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Actie-items (action items)

Taken die Omi uit gesprekken heeft afgeleid.

```bash
# alleen de openstaande
omi action-item list --open

# markeer als voltooid
omi action-item complete <ACTION_ITEM_ID>
```

### Doelen (goals)

```bash
# lijst van doelen
omi goal list

# registreer een nieuwe voortgangswaarde (vereist BEIDE argumenten: doel en waarde)
omi goal progress <GOAL_ID> 25

# geschiedenis van wijzigingen
omi goal history <GOAL_ID>
```

---

## Vragen in natuurlijke taal (`ask`)

Een apart commando op topniveau: het neemt een vraag in natuurlijke taal,
en het antwoord wordt opgebouwd uit uw gesprekken.

```bash
omi ask "wat heb ik besloten over de verhuizing"
omi --json ask "welke actie-items beloofde ik deze week af te ronden"
```

---

## 4. JSON en scripts (`--json`)

`omi-cli` kan machine-leesbare JSON produceren. De optie `--json` is **globaal**
en moet **vóór** het subcommando worden geplaatst.

```bash
# herinneringen: extraheer id, tekst en categorie
omi --json memory list | jq '.[] | {id, content, category}'

# titels van recente gesprekken
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# openstaande actie-items
omi --json action-item list --open | jq '.'
```

> **Veelgemaakte fout.** `--json` komt vóór het subcommando, niet erna.
> * Correct: `omi --json memory list`
> * Fout: `omi memory list --json`

In de `--json`-modus verdwijnen voortgangsberichten en spinners voor mensen —
stdout bevat slechts één geldig JSON-document. Fouten gaan naar stderr
in de vorm `{"error": "...", "detail": "..."}`.

---

## 5. Exit-codes

Stabiele exit-codes om in scripts op te beslissen.

| Code | Betekenis |
| :--- | :--- |
| `0` | Succes |
| `1` | Gebruiksfout (verkeerde vlag, verplicht argument ontbreekt) |
| `2` | Authenticatie mislukt — inloggen vereist |
| `3` | Server-/netwerkfout |
| `4` | Snelheidslimiet — probeer later opnieuw |
| `5` | Bron niet gevonden |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "die herinnering bestaat niet" ;;
    *) echo "fout $code" ;;
  esac
fi
```

---

## 6. Profielen en configuratie

Heeft u meerdere accounts of omgevingen, scheid ze dan met profielen.
Instellingen worden opgeslagen in `~/.omi/config.toml`.

```bash
# inloggen op het persoonlijke profiel
omi --profile personal auth login

# inloggen op het werkprofiel
omi --profile work auth login

# voer een commando uit in een specifiek profiel
omi --profile work memory list
```

Het gebruikte profiel wordt in deze volgorde bepaald: de optie `--profile` (of `-p`)
gaat vóór op alles; dan de omgevingsvariabele `OMI_PROFILE`; dan het actieve profiel
in `~/.omi/config.toml`; en ten slotte het profiel `default` als terugval.

Bekijk en wijzig de configuratie zelf:

```bash
# wat er nu is ingesteld
omi config show

# waar het configuratiebestand staat
omi config path

# wijzig een waarde
omi config set api_base https://api.omi.me
```

---

## 7. Volgende stappen

* [`agent_quickstart.md`](./agent_quickstart.md) — hoe u `omi-cli` aan een AI-agent koppelt.
* [`shell_examples.sh`](./shell_examples.sh) — kant-en-klare shell-voorbeelden.
* [Omi-documentatie](https://docs.omi.me/doc/developer/cli/introduction) — de volledige commandoreferentie.
