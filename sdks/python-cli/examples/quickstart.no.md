# omi-cli hurtigstartveiledning (Norwegian Quickstart)

> Praktisk veiledning for å samhandle med Omi direkte fra terminalen — utviklet for utviklere og autonome AI-agenter.

`omi-cli` er det offisielle kommandolinjegrensesnittet for [Omi](https://omi.me) sitt utvikler-API. Det lar deg administrere systemets fire kjernekomponenter på en strukturert og automatiserbar måte: minner (memories), samtaler (conversations), oppgaver/handlinger (action items) og mål (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Offisiell dokumentasjon:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kildekode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installasjon

For å unngå avhengighetskonflikter og kjøre CLI-verktøyet i et isolert miljø, anbefales `pipx`:

```bash
# Anbefalt: isolert installasjon med pipx
pipx install omi-cli

# Alternativt med standard pip
pip install omi-cli
```

> **Merk: Pakkenavn vs. Kommandonavn**
> * Pakkenavnet på PyPI er **`omi-cli`** (navnet `omi` tilhører en urelatert pakke).
> * Kommandoen du kjører i terminalen er derimot direkte **`omi`**.

Bekreft at installasjonen fungerer:

```bash
omi --version
omi --help
```

---

## 2. Autentisering (Authentication)

`omi-cli` støtter to primære metoder for autentisering:

| Metode | Bruksområde | Eksempel |
| :--- | :--- | :--- |
| **Utvikler-API-nøkkel (`omi_dev_*`)** | Skript, CI/CD, headless-servere, AI-agenter | `omi auth login --api-key ...` eller `OMI_API_KEY` |
| **Nettleser-OAuth (Google/Apple)** | Lokale arbeidsstasjoner og utviklere | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktiv innlogging
Kjør uten flagg for å velge metode interaktivt:

```bash
omi auth login
# 1) Browser — Åpner nettleseren for Google-innlogging (bruk `--provider apple` for Apple)
# 2) API key — Lim inn API-nøkkel fra app.omi.me
```

### Direkte innlogging via nettleser
```bash
# Standard Google-innlogging
omi auth login --browser

# Alternativ Apple-innlogging
omi auth login --browser --provider apple
```

### Bruk av utvikler-API-nøkkel
Opprett en nøkkel i [app.omi.me](https://app.omi.me) under **Developer → API Keys**:

```bash
# Lagre nøkkelen i den aktive lokale profilen
omi auth login --api-key omi_dev_ditt_faktiske_token_her

# Eller angi som miljøvariabel (best for containere og CI/CD)
# Merk: Hvis en aktiv lokal profil allerede har lagret legitimasjon, kjør `omi auth logout` først.
export OMI_API_KEY="omi_dev_ditt_faktiske_token_her"
```

### Kontrollere autentiseringsstatus
* `omi auth status`: Viser aktiv profil og maskert legitimasjon (kjører lokalt/frakoblet; utløpsdato gjelder kun OAuth-tokens).
* `omi auth whoami`: Sender en forespørsel til Omi-serveren for å verifisere gyldighet (krever nettverk).

```bash
omi auth status
omi auth whoami
```

Logge ut:
```bash
omi auth logout
# Hvis OMI_API_KEY er definert i miljøet, fjern den også (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Kjernekommandoer

### Minner (Memories)
Strukturerte fakta og kontekstuelle observasjoner Omi har lagret:

```bash
# List ut minner
omi memory list

# Opprett et nytt minne med kategori
omi memory create "Foretrekker konsise tekniske svar med Python-eksempler" --category work

# Hent et spesifikt minne med ID
omi memory get <MEMORY_ID>
```

### Samtaler (Conversations)
Taleopptak, transkripsjoner og dialoger registrert av Omi-enheter:

```bash
# List ut de siste 5 samtalene
omi conversation list --limit 5

# Hent detaljer for en samtale inkludert full transkripsjon
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Oppgaver og Handlinger (Action Items)
Gjøremål automatisk utledet fra samtaler:

```bash
# List ut åpne oppgaver
omi action-item list --open

# Marker en oppgave som fullført
omi action-item complete <ACTION_ITEM_ID>
```

### Mål (Goals)
Framdriftsindikatorer og langsiktige mål:

```bash
# List ut aktive mål
omi goal list

# Opprett et nytt numerisk mål
omi goal create "Drikk 2L vann daglig" --type numeric --target 2 --unit liters
```

---

## 4. Strukturert automatisering og JSON-utdata (`--json`)

`omi-cli` er bygget for automatisering i rørledninger og verktøykjeder. Det globale `--json`-flagget returnerer ren, maskinlesbar JSON:

```bash
# List minner som JSON og filtrer med jq
omi --json memory list | jq '.[] | {id, content, category}'

# Hent titler på de siste samtalene
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Se alle åpne oppgaver i rå JSON
omi --json action-item list --open | jq '.'
```

> **Viktig syntaksregel:**
> `--json`-flagget er en **global opsjon** og må plasseres **før** underkommandoen:
> * Riktig: `omi --json memory list`
> * Feil: `omi memory list --json`

### Eksportere til fil
For å unngå at ANSI-farger eller kontrolltegn forurenser filer, omdiriger stdout direkte i skallet:

```bash
# Eksporter minner direkte til en ren JSON-fil
omi --json memory list > minner.json
```

---

## 5. Avslutningskoder (Exit Codes Contract)

For pålitelig feilhåndtering i CI/CD og skript følger `omi-cli` en streng kontrakt for avslutningskoder (se `omi_cli/errors.py`):

| Kode | Navn | Beskrivelse og eksempel |
| :---: | :--- | :--- |
| `0` | **Suksess (`EXIT_OK`)** | Operasjonen ble fullført uten feil. |
| `1` | **Bruksfeil (`EXIT_USAGE`)** | Ugyldige flagg eller valideringsfeil i applikasjonen (f.eks. gjensidig utelukkende `--browser` og `--api-key`). |
| `2` | **Autentiseringsfeil / Syntaksfeil (`EXIT_AUTH`)** | Manglende eller ugyldig legitimasjon, utløpt sesjon, eller ukjente Click-opsjoner. |
| `3` | **Serverfeil (`EXIT_SERVER`)** | HTTP 5xx fra Omi-serveren eller nettverksbrudd. |
| `4` | **Hastighetsbegrensing (`EXIT_RATE_LIMITED`)** | HTTP 429 — for mange forespørsler på kort tid. |
| `5` | **Ikke funnet (`EXIT_NOT_FOUND`)** | HTTP 404 — etterspurt ressurs (minne, samtale, oppgave) finnes ikke. |

---

## 6. Eksempler for ulike skallmiljøer

### Bash / Zsh (Linux / macOS)
```bash
# Sett API-nøkkel for sesjonen
export OMI_API_KEY="omi_dev_ditt_faktiske_token_her"

# Kjør kommando og kontroller avslutningskode
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Feil under henting av minner fra Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# Definer miljøvariabel i PowerShell
$env:OMI_API_KEY = "omi_dev_ditt_faktiske_token_her"

# Konverter JSON-utdata direkte til PowerShell-objekt
$minner = omi --json memory list | ConvertFrom-Json
$minner | Select-Object id, content, category

# Feilsjekk med $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi-kommandoen feilet med avslutningskode $LASTEXITCODE."
}
```

---

## 7. Lokal Desktop API-integrasjon (Omi Desktop)

Når Omi Desktop kjører lokalt på maskinen din (standard port 47778), kan du samhandle direkte med den lokale konteksten uten å gå via skyen:

```bash
# Konfigurer lokal API-tilkobling (bruk miljøvariabler for å beskytte token)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Skriv inn Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Bekreft status for lokal tilkobling
omi --json local status

# Søk i lokal visuell skjermhistorikk
omi --json local search-screen "Kvartalsrapport" --days 7 --app Safari
```

---

## 8. Administrasjon av flere profiler (Profiles)

Bruk `--profile` for å veksle sømløst mellom personlige kontoer, jobbprofiler eller testmiljøer. Innstillingene lagres i `~/.omi/config.toml`:

```bash
# Opprett og logg inn på personlig profil
omi --profile personal auth login

# Opprett og logg inn på jobbprofil
omi --profile work auth login

# Kjør kommando med spesifikk profil
omi --profile work memory list

# Bruk et tilpasset endepunkt for testing
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Sikkerhetsretningslinjer og beste praksis

* **Unngå hardkoding av nøkler:** Sjekk aldri API-nøkler (`omi_dev_*`) inn i Git-repositorier. Bruk `.env`-filer som er lagt til i `.gitignore`, eller sikre hemmelighetshåndterere.
* **Beskytt skallhistorikken:** Unngå å sende nøkler som rene kommandolinjeargumenter på delte servere; bruk interaktiv innlogging eller `OMI_API_KEY`.
* **Sikre mappetillatelser:** På Unix/macOS, sørg for at konfigurasjonskatalogen har begrensede rettigheter:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Sesjonssletting:** Ved fjerning av midlertidige miljøer, husk å fjerne miljøvariabelen:
  ```bash
  unset OMI_API_KEY
  ```
