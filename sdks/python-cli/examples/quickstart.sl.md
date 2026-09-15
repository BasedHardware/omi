# omi-cli Vodnik za hitri začetek (Slovenian Quickstart)

> Praktični vodnik za uporabo Omi neposredno iz terminala — zasnovan za razvijalce in avtonomne AI agente.

`omi-cli` je uradni vmesnik ukazne vrstice (CLI) za razvijalski API platforme [Omi](https://omi.me). Omogoča neposreden in strukturiran dostop do 4 ključnih virov Omi: spomini (*memories*), pogovori (*conversations*), opravila/dejanja (*action items*) in cilji (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Uradna dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorna koda:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Namestitev

Za zagotovitev izoliranega okolja in preprečevanje sporov s sistemskimi odvisnostmi Python je priporočena namestitev z orodjem `pipx`:

```bash
# Priporočeno: izolirana namestitev prek pipx
pipx install omi-cli

# Alternativna namestitev z orodjem pip (npr. znotraj virtualnega okolja)
pip install omi-cli
```

> **Pomembno razlikovanje: Ime paketa v primerjavi z imenom ukaza**
> * Uradno ime distribucijskega paketa na PyPI je **`omi-cli`** (paket `omi` je ločen in nepovezan projekt).
> * Ukaz, ki se izvaja v terminalu, pa je: **`omi`**.

Preverite pravilnost namestitve s prikazom različice in navodil za pomoč:

```bash
omi --version
omi --help
```

---

## 2. Avtentikacija (Authentication)

`omi-cli` podpira dva glavna načina preverjanja pristnosti:

| Način | Primernost | Primer ukaza |
| :--- | :--- | :--- |
| **Razvijalski API ključ (`omi_dev_*`)** | Skripte, CI/CD sistemi, strežniki, AI agenti | `omi auth login --api-key ...` ali `OMI_API_KEY` |
| **OAuth prijava prek brskalnika** | Lokalni razvoj na osebni delovni postaji | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktivna prijava

Zagon ukaza brez zastavic ponudi interaktivni meni za izbiro načina prijave:

```bash
omi auth login
# 1) Browser — Prijava prek brskalnika (Google ali Apple)
# 2) API key — Vnos razvijalskega ključa iz app.omi.me
```

### Prijava prek spletnega brskalnika

```bash
# Privzeta prijava z računom Google
omi auth login --browser

# Alternativna prijava z računom Apple
omi auth login --browser --provider apple
```

### Prijava z razvijalskim API ključem

Ustvarite svoj API ključ na nadzorni plošči [app.omi.me](https://app.omi.me) v razdelku **Developer → API Keys**:

```bash
# Shranjevanje ključa v trenutni lokalni profil
omi auth login --api-key omi_dev_vas_kljuc_tukaj

# Ali z uporabo okoljske spremenljivke (priporočeno za Docker vsebnike in CI/CD cevovode):
export OMI_API_KEY="omi_dev_vas_kljuc_tukaj"
```

> **Opomba o prednosti:** Če ima aktivni profil že shranjen API ključ, ima ta prednost pred okoljsko spremenljivko. Za uporabo `OMI_API_KEY` se najprej odjavite z `omi auth logout` ali uporabite nov profil.

### Preverjanje stanja prijave

* `omi auth status`: Lokalni pregled aktivnega profila in maskiranega identifikatorja (deluje brez povezave).
* `omi auth whoami`: Preveri veljavnost seje neposredno na strežniku Omi prek omrežne zahteve.

```bash
omi auth status
omi auth whoami
```

### Odjava (Logout)

Za izbris lokalno shranjenih poverilnic uporabite:

```bash
omi auth logout
# Če ste uporabili okoljsko spremenljivko OMI_API_KEY, jo odstranite iz seje:
unset OMI_API_KEY
```

> **Varnostna opomba:** Konfiguracija se shrani v datoteko `~/.omi/config.toml`. Na sistemih Unix/Linux je priporočljivo nastaviti ustrezne pravice: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Osnovni ukazi

### Spomini (Memories)

Beleženje in pridobivanje trajnih kontekstualnih ugotovitev ter dejstev:

```bash
# Seznam shranjenih spominov
omi memory list

# Ustvarjanje novega spomina
omi memory create "Uporabnik ima raje jedrnate odgovore z zgledi v Pythonu" --category work

# Pridobivanje podrobnosti določenega spomina
omi memory get <ID_SPOMINA>
```

### Pogovori (Conversations)

Zabeleženi avdio pogovori in njihovi prepisi z naprav Omi:

```bash
# Prikaz zadnjih 5 pogovorov
omi conversation list --limit 5

# Pridobitev pogovora skupaj s celotnim besedilnim prepisom
omi conversation get <ID_POGOVORA> --include-transcript
```

### Opravila in dejanja (Action Items)

Naloge, samodejno prepoznane in izluščene iz pogovorov:

```bash
# Seznam odprtih opravil
omi action-item list --open

# Označevanje opravila kot dokončanega
omi action-item complete <ID_OPRAVILA>
```

### Cilji (Goals)

Spremljanje dolgoročnih ciljev in napredka:

```bash
# Seznam aktivnih ciljev
omi goal list

# Ustvarjanje novega količinskega cilja (naslov je pozicijski argument)
omi goal create "Dnevni vnos vode" --type numeric --target 2500 --unit "ml"
```

---

## 4. Strukturirana avtomatizacija in izhod JSON (`--json`)

`omi-cli` omogoča preprosto integracijo v avtomatizirane skripte in sisteme AI agentov. Z globalno zastavico `--json` dobite čist izhod v formatu JSON, ki ga lahko obdelate z orodji, kot je `jq`:

```bash
# Pridobivanje spominov v formatu JSON in filtriranje z jq
omi --json memory list | jq '.[] | {id, content, category}'

# Pridobitev naslovov zadnjih 5 pogovorov
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Prikaz odprtih opravil
omi --json action-item list --open | jq '.'
```

> **Ključno pravilo skladnje:**
> Zastavica `--json` je **globalna možnost**, kar pomeni, da jo morate vedno postaviti **pred** podukaz:
> * Pravilno: `omi --json memory list`
> * Napačno: `omi memory list --json`

### Paginacija in izvoz podatkov

Pri delu z večjimi količinami podatkov uporabite parametra `--limit` in `--offset`:

```bash
# Zajem podatkov po straneh
omi --json memory list --limit 25 --offset 0 > spomini-stran-1.json
omi --json memory list --limit 25 --offset 25 > spomini-stran-2.json
```

Preusmeritev v datoteko ustvari ali prepiše lokalno datoteko. Pred obdelavo vedno preverite izhodno kodo ukaza. Napake se izpišejo v standardni tok za napake (`stderr`), zato prazna datoteka ne pomeni nujno odsotnosti podatkov. Izvožene datoteke lahko vsebujejo osebne podatke, zato jih varujte v skladu s svojimi varnostnimi pravili.

---

## 5. Izhodne kode (Exit Codes Contract)

`omi-cli` sledi natančni specifikaciji izhodnih kod za zanesljivo obravnavo napak v skriptih in sistemih CI/CD (skladno z `omi_cli/errors.py`):

| Koda | Oznaka | Pomen in opis |
| :---: | :--- | :--- |
| `0` | **Uspeh (`EXIT_OK`)** | Ukaz se je uspešno izvedel brez napak. |
| `1` | **Napaka pri uporabi / Validacija (`EXIT_USAGE`)** | Validacijska napaka na ravni aplikacije (`UsageError`, npr. sočasna uporaba medsebojno izključujočih se možnosti `--browser` in `--api-key`). |
| `2` | **Napaka pri avtentikaciji / Parser (`EXIT_AUTH`)** | Manjkajoče poverilnice, potekel žeton ali nezadostne pravice. Sintaktične napake in neveljavne vrednosti možnosti razčlenjevalnika Click/Typer (neznane možnosti, napačne vrednosti ali manjkajoči obvezni argumenti) prav tako vrnejo kodo 2. |
| `3` | **Napaka strežnika ali omrežja (`EXIT_SERVER`)** | Odgovor HTTP 5xx s strežnika Omi ali prekinitev omrežne povezave. |
| `4` | **Presežena omejitev zahtev (`EXIT_RATE_LIMITED`)** | Odgovor HTTP 429 — preveč poslanih zahtev v kratkem časovnem oknu. |
| `5` | **Vir ni najden (`EXIT_NOT_FOUND`)** | Odgovor HTTP 404 — iskani vir ne obstaja. |

---

## 6. Primeri za različna terminalska okolja

### Bash / Zsh (Linux in macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Uspešno prejetih $(jq 'length' /tmp/memories.json) spominov."
else
    code=$?
    echo "Napaka pri pridobivanju spominov (koda izhoda: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Ukaz ni uspel z izhodno kodo $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Podatki so bili uspešno shranjeni."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Prišlo je do napake z izhodno kodo %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Operacija se je uspešno zaključila.
```

---

## 7. Upravljanje profilov in testno okolje (Staging)

Možnost `--profile` omogoča sočasno vodenje več neodvisnih konfiguracij (npr. osebne, službene ali testne). Za trajno konfiguracijo testnega okolja (staging) nastavite osnovni naslov profila:

```bash
# Trajna nastavitev osnovnega URL-ja za profil staging
omi --profile staging config set api_base https://api.staging.omi.me

# Prijava v profil za testno okolje (staging)
omi --profile staging auth login --api-key omi_dev_staging_kljuc

# Izvedba ukazov v profilu staging (trajno usmerjeno na testno okolje)
omi --profile staging memory list

# Alternativno, enkratni prepis za posamezen ukaz:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Pomembno opozorilo o `--api-base`:** Zastavica `--api-base` deluje le kot začasni prepis za posamezen ukaz in se ne shrani samodejno v konfiguracijo profila. Za trajno veljavnost jo nastavite z ukazom `config set api_base <url>`.

---

## 8. Integracija z lokalnim namiznim API-jem (Local Desktop API)

Če se namizna aplikacija Omi izvaja na istem računalniku, lahko komunicirate neposredno z lokalnim strežnikom brez pošiljanja podatkov v oblak. Pred izvajanjem ukaza `omi local status` ali iskanjem obvezno nastavite naslov vozlišča in dostopni žeton:

```bash
# 1. Nastavitev lokalnega naslova (privzeta vrata 47778) in žetona:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="vas_lokalni_zeton"

# Alternativno, trajna nastavitev v profilu:
# omi local configure --url http://127.0.0.1:47778 --token "vas_lokalni_zeton"

# 2. Preverjanje stanja lokalne storitve (zahteva vnaprej nastavljena naslov in žeton)
omi local status

# 3. Iskanje po zgodovini zaslonskih dejavnosti po poizvedbi in aplikaciji
omi local search-screen "tedenski sestanek" --days 1 --app "Slack"
```

---

## 9. Najboljše varnostne prakse in priporočila

1. **Položaj stikala `--json`:** Vedno ga navedite pred podukazom (`omi --json memory list`).
2. **Obravnava izhodnih kod:** V avtomatizacijah dosledno preverjajte in obravnavajte izhodne kode od 1 do 5.
3. **Varnost poverilnic:** Nikoli ne objavljajte API ključev v javnih repozitorijih. V produkciji in CI/CD cevovodih uporabljajte okoljsko spremenljivko `OMI_API_KEY`.
