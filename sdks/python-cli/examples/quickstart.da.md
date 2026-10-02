# omi-cli — dansk hurtigstartguide

> Praktisk guide til at arbejde med Omi fra terminalen. Velegnet til både mennesker og AI-agenter.

`omi-cli` er den officielle kommandolinje-klient til [Omi](https://omi.me)s udvikler-API.
Den giver hurtig og scriptvenlig adgang til Omi's fire kerneentiteter:
erindringer, samtaler, opgaver og mål.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kildekode:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Den anbefalede metode er `pipx`: den installerer værktøjet i et isoleret miljø,
så dets afhængigheder ikke konflikter med dine projekter.

```bash
# anbefalet: installation via pipx
pipx install omi-cli

# eller via pip
pip install omi-cli
```

> **Vigtigt: pakkenavn og kommandonavn er forskellige.**
> * Der installeres pakken **`omi-cli`** (den separate pakke `omi` er et andet, urelateret projekt).
> * Efter installation kører du kommandoen **`omi`**.

Tjek at alt virker:

```bash
omi --version
omi --help
```

---

## 2. Autentificering

`omi-cli` understøtter to måder at logge ind.

| Metode | Velegnet til | Kommando |
| :--- | :--- | :--- |
| **Udviklernøgle (`omi_dev_*`)** | CI/CD, scripts, AI-agenter | `omi auth login --api-key ...` eller miljøvariabel |
| **Browser-login (Google/Apple)** | Arbejde på sin egen computer | `omi auth login --browser` |

### Interaktivt login

Uden flag spørger kommandoen selv, hvilken metode du vil bruge:

```bash
omi auth login
# 1) Browser — log ind med Google eller Apple (nemt for mennesker)
# 2) API key — indsæt udviklernøgle fra app.omi.me (nemt for agenter og CI)
```

Ved valg af nøgle maskeres input, så nøglen ikke efterlades i terminalhistorikken.

### Direkte via browser

```bash
omi auth login --browser
```

### Via udviklernøgle

Nøglen hentes på [app.omi.me](https://app.omi.me) under **Developer → API Keys**.

```bash
# gem nøglen i konfigurationen
omi auth login --api-key omi_dev_...

# eller send den via miljøet — foretrukket til CI/CD og containere
export OMI_API_KEY=omi_dev_...
```

Miljøvariablen `OMI_API_KEY` bruges, når der ikke er gemt en nøgle i den aktive profil,
så i en container behøver intet skrives til disken. Hvis profilen allerede har en nøgle,
har den prioritet over miljøvariablen.

### Tjek login

To kommandoer besvarer forskellige spørgsmål, og de bør ikke forveksles:

* `omi auth status` — hvad der ligger **lokalt**: profil, maskeret nøgle, udløbsdato.
  Virker uden netværk.
* `omi auth whoami` — henvendelse **til Omi-serveren**: tjekker, at nøglen faktisk
  accepteres. Kræver netværk.

```bash
omi auth status    # lokal kontrol, offline
omi auth whoami    # kontrol på serveren
```

Opdater et udløbende token uden at logge ind igen (kun relevant for browser-login/OAuth):

```bash
omi auth refresh
```

Log ud:

```bash
omi auth logout
```

---

## 3. Grundlæggende kommandoer

### Erindringer (memories)

Fakta og viden, som systemet har husket om dig.

```bash
# liste over erindringer
omi memory list

# opret en ny
omi memory create "Brugeren foretrækker mørkt tema" --category lifestyle

# se en bestemt
omi memory get <MEMORY_ID>
```

### Samtaler (conversations)

Tale- og teksthistorik fra enheden eller appen.

```bash
# de seneste 5 samtaler
omi conversation list --limit 5

# en hel samtale med transskription
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Opgaver (action items)

Gøremål, som Omi har udledt af samtaler.

```bash
# kun åbne
omi action-item list --open

# markér som fuldført
omi action-item complete <ACTION_ITEM_ID>
```

### Mål (goals)

```bash
# liste over mål
omi goal list

# registrér en ny fremdriftsværdi (kræver BEGGE argumenter: mål og værdi)
omi goal progress <GOAL_ID> 25

# ændringshistorik
omi goal history <GOAL_ID>
```

---

## Stil spørgsmål med dine egne ord (`ask`)

En separat topniveau-kommando: stiller et spørgsmål i naturligt sprog,
og svaret bygges ud fra dine egne samtaler.

```bash
omi ask "hvad besluttede jeg omkring flytningen"
omi --json ask "hvilke opgaver lovede jeg at lukke i denne uge"
```

---

## 4. JSON og scripts (`--json`)

`omi-cli` kan levere maskinlæsbar JSON. Flaget `--json` er **globalt**
og placeres derfor **før** underkommandoen.

```bash
# erindringer: udtræk id, tekst og kategori
omi --json memory list | jq '.[] | {id, content, category}'

# titler på de seneste samtaler
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# åbne opgaver
omi --json action-item list --open | jq '.'
```

> **Almindelig fejl.** `--json` kommer før underkommandoen, ikke efter.
> * Korrekt: `omi --json memory list`
> * Forkert: `omi memory list --json`

I `--json`-tilstand udskrives der ikke andet end selve JSON'en til stdout —
det kan scripts stole på.

---

## 5. Exitkoder

Koderne er stabile, så logik i scripts og CI kan forgrene sig på dem.

| Kode | Betydning | Hvornår |
| :---: | :--- | :--- |
| `0` | Succes | Kommandoen blev udført |
| `1` | Kaldefejl | omi-clis egen validering (f.eks. både `--browser` og `--api-key` samtidigt, ugyldigt loginvalg, tom stdin) |
| `2` | Adgangsfejl | Ikke logget ind, ugyldig eller udløbet nøgle |
| `3` | Serverfejl | 5xx-svar, timeout, ingen forbindelse |
| `4` | For mange forespørgsler | 429 Too Many Requests |
| `5` | Ikke fundet | 404, id findes ikke |

> **Bemærk.** Ukendte flag og manglende argumenter fanges af Click og giver kode `2`.

Eksempel på kontrol i Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "nøglen virker"
else
  code=$?
  [ "$code" -eq 2 ] && echo "log ind igen"
  [ "$code" -eq 3 ] && echo "serveren er nede, prøv igen senere"
fi
```

---

## 6. Miljøvariabler

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_din_nøgle"

omi --json memory list --limit 10
```

For at nøglen indlæses i nye sessioner, tilføj linjen til `~/.bashrc` eller `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_din_nøgle"

# JSON-parsing med PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Til permanent opsætning:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_din_nøgle", "User")
```

---

## 7. Omi Desktop-appen lokalt

Hvis desktop-appen Omi kører, er en del data tilgængelig direkte,
uden om skyen.

```bash
# angiv adressen til det lokale API
omi local configure --url http://127.0.0.1:47778 --token DIN_TOKEN

# tjek at den svarer
omi --json local status

# søgning i skærmhistorikken
omi --json local search-screen "priser" --days 7 --app Safari

# skærmbillede efter id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# vilkårlig SQL mod den lokale database
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Arbejdsgang: først `local status`, derefter `local tools` — for at se tilgængelige
værktøjer og deres parametre, og først derefter kald.

---

## 8. Profiler

Hvis du har flere konti eller miljøer, adskil dem med profiler.
Indstillingerne gemmes i `~/.omi/config.toml`.

```bash
# login til personlig profil
omi --profile personal auth login

# login til arbejdsprofil
omi --profile work auth login

# kør en kommando i en bestemt profil
omi --profile work memory list
```

Se og ændr selve konfigurationen:

```bash
# hvad er konfigureret nu
omi config show

# hvor konfigurationsfilen ligger
omi config path

# ændr en værdi
omi config set api_base https://api.omi.me
```

---

## 9. Næste skridt

* [`agent_quickstart.md`](./agent_quickstart.md) — hvordan man kobler `omi-cli` til en AI-agent.
* [`shell_examples.sh`](./shell_examples.sh) — færdige eksempler til shellen.
* [Omi-dokumentation](https://docs.omi.me/doc/developer/cli/introduction) — den fulde kommandoreference.
