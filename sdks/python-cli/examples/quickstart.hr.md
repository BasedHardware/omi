# Brzi vodič za omi-cli (Croatian Quickstart)

`omi-cli` je službeno sučelje naredbenog retka (CLI) za platformu [Omi](https://www.omi.me) i Omi Developer API. Omogućuje sigurno upravljanje sjećanjima (memories), razgovorima, akcijskim stavkama / zadacima (action items) i ciljevima izravno iz terminala, automatiziranih skripti ili AI agenata.

---

## 1. Instalacija

Paket se distribuira na PyPI pod nazivom **`omi-cli`**, dok je naziv izvršne naredbe na vašem sustavu **`omi`**:

```bash
# Preporučena izolirana instalacija putem alata pipx:
pipx install omi-cli

# Ili standardna instalacija putem pip-a:
pip install omi-cli
```

Provjerite ispravnost instalacije i instaliranu verziju:

```bash
omi --version
omi --help
```

---

## 2. Autentifikacija

`omi-cli` podržava prijavu putem web preglednika (OAuth) ili izravno putem razvojnog API ključa (`omi_dev_*`).

### Opcija A: Prijava putem preglednika (preporučeno za korisnike)

Pokrenite interaktivnu prijavu putem zadanog Google računa ili Apple ID-a:

```bash
# Zadana prijava (Google OAuth)
omi auth login --browser

# Prijava putem Apple ID-a
omi auth login --browser --provider apple
```

### Opcija B: Prijava putem API ključa (prikladno za poslužitelje i CI/CD)

Razvojni API ključ možete generirati na portalu Omi u odjeljku **Developer → API Keys**. Svi ključevi počinju prefiksom `omi_dev_`.

```bash
# Spremanje ključa u lokalni profil
omi auth login --api-key omi_dev_vas_kljuc_ovdje

# Ili postavljanje varijable okruženja (idealno za kontejnere i automatizirane sustave):
export OMI_API_KEY="omi_dev_vas_kljuc_ovdje"
```

> **Napomena o prioritetu:** Ako aktivni profil već ima spremljen API ključ, on ima prednost pred varijablom okruženja. Za korištenje `OMI_API_KEY`, prvo se odjavite s `omi auth logout` ili upotrijebite novi profil.

### Provjera statusa autentifikacije

* `omi auth status`: Prikazuje aktivni profil i maskirani identifikator bez slanja mrežnih zahtjeva (radi offline).
* `omi auth whoami`: Šalje autentificirani zahtjev poslužitelju Omi radi potvrde valjanosti sesije (zahtijeva internetsku vezu).

```bash
omi auth status
omi auth whoami
```

### Odjava (Logout)

Za uklanjanje lokalno spremljenih vjerodajnica upotrijebite:

```bash
omi auth logout
# Ako ste koristili varijablu okruženja OMI_API_KEY, uklonite je iz sesije:
unset OMI_API_KEY
```

> **Sigurnosna napomena:** Konfiguracijska datoteka sprema se u `~/.omi/config.toml`. Preporučuje se zaštita datotečnih dozvola: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Osnovne naredbe

### Sjećanja (Memories)

Kontekstualne bilješke i uvidi koje bilježi Omi:

```bash
# Prikaz popisa spremljenih sjećanja
omi memory list

# Stvaranje novog sjećanja
omi memory create "Korisnik preferira sažete tehničke odgovore s Python primjerima" --category work

# Dohvaćanje pojedinog sjećanja prema identifikatoru
omi memory get <MEMORY_ID>
```

### Razgovori (Conversations)

Zapisani razgovori i prijepisi zvuka:

```bash
# Popis nedavnih razgovora
omi conversation list

# Popis razgovora s uključenim cjelovitim prijepisom (transcript)
omi conversation list --include-transcript

# Dohvaćanje pojedinog razgovora
omi conversation get <CONVERSATION_ID>
```

### Akcijske stavke / Zadaci (Action Items)

Obveze i zadaci izdvojeni iz razgovora:

```bash
# Popis svih akcijskih stavki
omi action-item list

# Prikaz samo otvorenih (nedovršenih) zadataka
omi action-item list --open

# Označavanje zadatka dovršenim
omi action-item complete <ACTION_ITEM_ID>
```

### Ciljevi (Goals)

Postavljanje i praćenje osobnih ili poslovnih ciljeva:

```bash
# Popis ciljeva
omi goal list

# Stvaranje novog brojčanog cilja (naziv se zadaje kao pozicijski argument)
omi goal create "Dnevni unos vode" --type numeric --target 2500 --unit "ml"
```

---

## 4. Rad s formatom JSON i cjevovodi

### Globalna zastavica `--json`

Zastavica `--json` je globalna opcija CLI sučelja i **uvijek se mora navesti prije podnaredbe**:

```bash
# Ispravno postavljanje:
omi --json memory list

# Filtriranje izlaza pomoću alata jq:
omi --json memory list --limit 10 | jq '.[].content'
```

### Straničenje (Pagination)

Za dohvaćanje većih skupova podataka koristite parametre `--limit` i `--offset`:

```bash
# Prva stranica (stavke 0–24)
omi --json memory list --limit 25 --offset 0 > sjecanja-stranica-1.json

# Druga stranica (stavke 25–49)
omi --json memory list --limit 25 --offset 25 > sjecanja-stranica-2.json
```

Preusmjeravanje izlaza prepisuje odredišnu datoteku. Prije daljnje obrade uvijek provjerite izlazni kod naredbe.

---

## 5. Izlazni kodovi (Exit Codes Contract)

`omi-cli` koristi strogo definiran ugovor izlaznih kodova za pouzdanu obradu pogrešaka u skriptama i CI/CD cjevovodima (prema `omi_cli/errors.py`):

| Kod | Naziv | Opis i značenje |
| :---: | :--- | :--- |
| `0` | **Uspjeh (`EXIT_OK`)** | Naredba je uspješno dovršena bez pogrešaka. |
| `1` | **Pogreška pri korištenju / Validacija (`EXIT_USAGE`)** | Validacijska pogreška na razini aplikacije (`UsageError`, npr. istovremeno zadavanje međusobno isključivih zastavica `--browser` i `--api-key`). |
| `2` | **Pogreška autentifikacije / Parser (`EXIT_AUTH`)** | Nedostaju vjerodajnice, istekao ključ ili nedovoljne ovlasti pristupa. Sintaktičke pogreške i nevažeće vrijednosti opcija Click/Typer parsera (nepoznate opcije, neispravne vrijednosti ili nedostajući argumenti) također se mapiraju na kod 2. |
| `3` | **Pogreška poslužitelja ili mreže (`EXIT_SERVER`)** | HTTP 5xx odgovor s poslužitelja Omi ili prekid mrežne veze. |
| `4` | **Ograničenje brzine zahtjeva (`EXIT_RATE_LIMITED`)** | HTTP 429 odgovor — prevelik broj zahtjeva u kratkom vremenskom razdoblju. |
| `5` | **Resurs nije pronađen (`EXIT_NOT_FOUND`)** | HTTP 404 odgovor — traženi podatak ne postoji. |

---

## 6. Primjeri za različita terminalska okruženja

### Bash / Zsh (Linux i macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Uspješno dohvaćeno $(jq 'length' /tmp/memories.json) sjećanja."
else
    code=$?
    echo "Pogreška pri dohvaćanju sjećanja (exit code: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Naredba nije uspjela s kodom $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Podaci su uspješno spremljeni."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Došlo je do pogreške s kodom %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Naredba je uspješno izvršena.
```

---

## 7. Upravljanje profilima i testno okruženje

Opcija `--profile` omogućuje istovremeno održavanje više konfiguracija. Za trajno konfiguriranje testnog okruženja (staging) postavite bazni URL profila:

```bash
# Trajno postavljanje baznog URL-a za staging profil
omi --profile staging config set api_base https://api.staging.omi.me

# Prijava u profil testnog okruženja (staging)
omi --profile staging auth login --api-key omi_dev_staging_kljuc

# Izvršavanje naredbi unutar profila staging (usmjereno na staging)
omi --profile staging memory list

# Alternativno, jednokratno premošćivanje po pojedinoj naredbi:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Napomena o `--api-base`:** Zastavica `--api-base` djeluje samo kao privremeno premošćivanje po pojedinoj naredbi i ne sprema se automatski u profil. Za trajnu upotrebu postavite je pomoću naredbe `config set api_base <url>`.

---

## 8. Integracija s lokalnim Desktop API-jem

Kada je pokrenuta desktop aplikacija Omi, možete izravno komunicirati s lokalnim poslužiteljem bez slanja prometa na oblak. Prije pozivanja naredbe `omi local status` ili pretraživanja, obavezno konfigurirajte adresu lokalnog čvora i token:

```bash
# 1. Postavljanje lokalnog poslužitelja (zadani port 47778) i tokena:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="vas_lokalni_token"

# Alternativno, trajno spremanje u profil:
# omi local configure --url http://127.0.0.1:47778 --token "vas_lokalni_token"

# 2. Provjera statusa lokalnog desktop čvora (zahtijeva prethodno postavljene parametre)
omi local status

# 3. Pretraživanje aktivnosti na zaslonu prema upitu i aplikaciji
omi local search-screen "rasprava o projektu" --days 1 --app "Slack"
```

---

## 9. Sažetak najboljih praksi

1. **Položaj prepisivača `--json`:** Uvijek ga navedite prije podnaredbe (`omi --json memory list`).
2. **Praćenje izlaznih kodova:** U skriptama i automatizacijama provjeravajte kodove 1 do 5.
3. **Zaštita ključeva:** Nikada nemojte pohranjivati API ključeve u javna spremišta koda. Koristite `OMI_API_KEY` u produkciji i CI/CD cjevovodima.
