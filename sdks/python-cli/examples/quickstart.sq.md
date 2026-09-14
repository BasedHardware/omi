# omi-cli Udhëzues për fillim të shpejtë (Albanian Quickstart)

> Udhëzues praktik për përdorimin e Omi drejtpërdrejt nga terminali — i ndërtuar për zhvillues dhe agjentë autonomë të inteligjencës artificiale (AI).

`omi-cli` është ndërfaqja zyrtare e rreshtit të komandave (CLI) për API-në e zhvilluesve të [Omi](https://omi.me). Ajo ofron qasje të strukturuar në 4 burimet kryesore të Omi: kujtimet (*memories*), bisedat (*conversations*), detyrat konkrete (*action items*) dhe qëllimet (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentacioni zyrtar:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kodi burimor:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalimi

Për të garantuar një mjedis të izoluar dhe për të parandaluar konfliktet me varësitë e paketave të sistemit Python, rekomandohet fuqimisht përdorimi i `pipx`:

```bash
# Metoda e rekomanduar: instalim i izoluar përmes pipx
pipx install omi-cli

# Instalimi alternativ me pip (p.sh. brenda një mjedisi virtual)
pip install omi-cli
```

> **Sqarim thelbësor: Emri i paketës kundrejt emrit të komandës**
> * Emri zyrtar i paketës në regjistrin PyPI është **`omi-cli`** (paketa me emrin `omi` është një projekt krejtësisht i ndryshëm dhe i palidhur).
> * Komanda që ekzekutohet në terminal është drejtpërdrejt: **`omi`**.

Verifikoni instalimin duke kontrolluar versionin dhe menynë e ndihmës:

```bash
omi --version
omi --help
```

---

## 2. Autentikimi (Authentication)

`omi-cli` mbështet dy mënyra kryesore për vërtetimin e identitetit:

| Mënyra | Përdorimi ideal | Shembull komande |
| :--- | :--- | :--- |
| **Çelës API zhvilluesi (`omi_dev_*`)** | Skriptet, rrjedhat CI/CD, serverët headless, agjentët AI | `omi auth login --api-key ...` ose `OMI_API_KEY` |
| **Hyrje OAuth përmes shfletuesit** | Zhvillim vendor në kompjuterin personal | `omi auth login --browser` (Google) / `--provider apple` |

### Hyrje interaktive

Ekzekutimi i komandës pa parametra shtesë shfaq një meny interaktive:

```bash
omi auth login
# 1) Browser — Hyrje me shfletues (Google ose Apple)
# 2) API key — Vendosja e çelësit të marrë në app.omi.me
```

### Hyrje përmes shfletuesit të internetit

```bash
# Hyrje standarde me llogari Google
omi auth login --browser

# Hyrje alternative me profil Apple
omi auth login --browser --provider apple
```

### Hyrje me çelës API zhvilluesi

Gjeneroni një çelës API në panelin e kontrollit [app.omi.me](https://app.omi.me) te rubrika **Developer → API Keys**:

```bash
# Ruajtja e çelësit në profilin lokal aktiv
omi auth login --api-key omi_dev_celesi_juaj_ketu

# Ose duke e caktuar si ndryshore mjedisi (rekomandohet për kontejnerë Docker dhe sisteme CI/CD):
export OMI_API_KEY="omi_dev_celesi_juaj_ketu"
```

> **Shënim sigurie dhe prioriteti:**
> * Përdorimi i flamurit `--api-key` drejtpërdrejt në rreshtin e komandës e lë çelësin të dukshëm në historikun e terminalit (`shell history`) dhe proceset e sistemit. Në makina të përbashkëta preferoni ngjitjen interaktive (`omi auth login`) ose ndryshoren `OMI_API_KEY`.
> * Nëse profili aktiv ka tashmë një çelës të ruajtur, ai ka përparësi ndaj ndryshores së mjedisit. Për të aktivizuar `OMI_API_KEY`, dilni më parë me `omi auth logout` ose përdorni një profil të ri.

### Verifikimi i gjendjes së sesionit

* `omi auth status`: Shfaq profilin aktiv dhe identifikuesin e maskuar nga konfigurimi vendor (funksionon jashtë linje).
* `omi auth whoami`: Dërgon një kërkesë rrjeti te serverët Omi për të konfirmuar vlefshmërinë e sesionit.

```bash
omi auth status
omi auth whoami
```

### Dalje (Logout)

Për të fshirë kredencialet e ruajtura lokalisht:

```bash
omi auth logout
# Nëse keni përdorur ndryshoren e mjedisit OMI_API_KEY, hiqeni atë nga sesioni:
unset OMI_API_KEY
```

> **Shënim sigurie:** Skedari i konfigurimit ruhet te `~/.omi/config.toml`. Në sistemet Unix, rekomandohet kufizimi i lejeve: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Komandat kryesore

### Kujtimet (Memories)

Regjistrimi dhe kërkimi i fakteve, vëzhgimeve dhe kontekstit të përhershëm:

```bash
# Lista e kujtimeve të ruajtura
omi memory list

# Krijimi i një kujtimi të ri
omi memory create "Përdoruesi preferon përgjigje teknike koncize me shembuj në Python" --category work

# Marrja e një kujtimi të caktuar sipas identifikuesit
omi memory get <ID_KUJTIMI>
```

### Bisedat (Conversations)

Regjistrimet zanore dhe transkriptimet me tekst nga pajisjet Omi:

```bash
# Lista e 5 bisedave të fundit
omi conversation list --limit 5

# Marrja e bisedës së bashku me transkriptimin e plotë
omi conversation get <ID_BISEDE> --include-transcript
```

### Detyrat dhe veprimet konkrete (Action Items)

Njoftime dhe veprime të zbuluara automatikisht gjatë bisedave:

```bash
# Lista e detyrave të hapura
omi action-item list --open

# Shënimi i një detyre si të përfunduar
omi action-item complete <ID_DETYRE>
```

### Qëllimet (Goals)

Monitorimi i synimeve afatgjata dhe ecurisë:

```bash
# Lista e qëllimeve aktive
omi goal list

# Krijimi i një qëllimi sasior (titulli jepet si argument pozicional)
omi goal create "Konsumi ditor i ujit" --type numeric --target 2500 --unit "ml"
```

---

## 4. Automatizim i strukturuar dhe dalje JSON (`--json`)

`omi-cli` është i përshtatshëm për integrim të lehtë në skripte dhe rrjedha agjentësh AI. Flamuri global `--json` siguron dalje të pastër në formatin JSON për përpunim me vegla si `jq`:

```bash
# Marrja e kujtimeve në format JSON dhe filtrimi me jq
omi --json memory list | jq '.[] | {id, content, category}'

# Nxjerrja e titujve të 5 bisedave të fundit
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Lista e detyrave të hapura
omi --json action-item list --open | jq '.'
```

> **Rregull themelor sintakse:**
> Flamuri `--json` është një **opsion global** dhe duhet të vendoset gjithmonë **përpara** nënkomandës:
> * Saktë: `omi --json memory list`
> * Gabim: `omi memory list --json`

### Faqosja dhe eksportimi i të dhënave

Kur punoni me sasi të mëdha të dhënash, përdorni parametrat `--limit` dhe `--offset`:

```bash
# Marrja e të dhënave faqe pas faqeje
omi --json memory list --limit 25 --offset 0 > kujtime-faqe-1.json
omi --json memory list --limit 25 --offset 25 > kujtime-faqe-2.json
```

Ridrejtimi në skedar krijon ose mbishkruan skedarin vendor. Gjithmonë kontrolloni kodin e daljes përpara përpunimit të mëtejshëm. Mesazhet e gabimit dalin në rrjedhën standarde të gabimeve (`stderr`), ndaj një skedar bosh nuk garanton mungesën e të dhënave. Skedarët e eksportuar mund të përmbajnë të dhëna konfidenciale — ruajini ato sipas rregullave tuaja të sigurisë.

---

## 5. Kodet e daljes (Exit Codes Contract)

`omi-cli` zbaton një marrëveshje precize të kodeve të daljes për menaxhim të besueshëm gabimesh në skripte dhe sisteme CI/CD (në përputhje me `omi_cli/errors.py`):

| Kodi | Emërtimi | Kuptimi dhe përshkrimi |
| :---: | :--- | :--- |
| `0` | **Sukses (`EXIT_OK`)** | Komanda u ekzekutua me sukses pa asnjë gabim. |
| `1` | **Gabim përdorimi / Validim (`EXIT_USAGE`)** | Gabim validimi në nivel aplikacioni (`UsageError`, p.sh. përdorimi i njëkohshëm i opsioneve reciprokisht përjashtuese `--browser` dhe `--api-key`). |
| `2` | **Gabim autentikimi / Parser (`EXIT_AUTH`)** | Mungojnë kredencialet, çelësi ka skaduar ose mungojnë të drejtat. Gabimet e sintaksës dhe vlerat e pavlefshme të opsioneve të parserit Click/Typer (opsione të panjohura, vlera të pasakta ose argumente të munguara) kthejnë gjithashtu kodin 2. |
| `3` | **Gabim serveri ose rrjeti (`EXIT_SERVER`)** | Përgjigje gabimi HTTP 5xx nga serveri Omi ose ndërprerje e lidhjes së rrjetit. |
| `4` | **Kufiri i kërkesave u tejkalua (`EXIT_RATE_LIMITED`)** | Përgjigje HTTP 429 — shumë kërkesa të dërguara brenda një kohe të shkurtër. |
| `5` | **Burimi nuk u gjet (`EXIT_NOT_FOUND`)** | Përgjigje HTTP 404 — burimi i kërkuar nuk ekziston. |

---

## 6. Shembuj për mjedise të ndryshme terminali

### Bash / Zsh (Linux dhe macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "U morën me sukses $(jq 'length' /tmp/memories.json) kujtime."
else
    code=$?
    echo "Gabim gjatë marrjes së kujtimeve (kodi i daljes: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Komanda dështoi me kodin e daljes $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Të dhënat u ruajtën me sukses."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Ndodhi një gabim me kodin %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Operacioni përfundoi me sukses.
```

---

## 7. Menaxhimi i profileve dhe mjedisi i testimit (Staging)

Opsioni `--profile` lejon mbajtjen e disa konfigurimeve paralele (p.sh. personale, pune ose testimi). Për mjediset e testimit, caktoni URL-në bazë të përhershme të profilit:

```bash
# Caktimi i përhershëm i URL-së bazë për profilin staging
omi --profile staging config set api_base https://api.staging.omi.me

# Hyrje në profilin e testimit (staging)
omi --profile staging auth login --api-key omi_dev_staging_celes

# Ekzekutimi i komandave në profilin staging (i drejtuar përhershëm te mjedisi staging)
omi --profile staging memory list

# Ose anashkalim i përkohshëm për një komandë të caktuar:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Shënim i rëndësishëm për `--api-base`:** Flamuri `--api-base` vepron vetëm si anashkalim i përkohshëm për atë komandë dhe nuk ruhet automatikisht në konfigurim. Për përdorim të vazhdueshëm përdorni `config set api_base <url>`.

---

## 8. Integrimi me API-në vendase të desktopit (Local Desktop API)

Nëse aplikacioni Omi Desktop po ekzekutohet në të njëjtin kompjuter, mund të komunikoni drejtpërdrejt me serverin lokal pa i dërguar të dhënat në re (cloud). Përpara komandës `omi local status` ose kërkimeve, sigurohuni të keni caktuar adresën dhe tokenin e qasjes:

```bash
# 1. Caktimi i adresës lokale (porta e paracaktuar 47778) dhe tokenit:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="tokeni_juaj_vendas"

# Ose ruajtja e përhershme në profil:
# omi local configure --url http://127.0.0.1:47778 --token "tokeni_juaj_vendas"

# 2. Kontrolli i gjendjes së shërbimit lokal (kërkon parametrat e caktuar paraprakisht)
omi local status

# 3. Kërkimi në historikun e ekranit sipas pyetjes dhe aplikacionit
omi local search-screen "takimi javor" --days 1 --app "Slack"
```

---

## 9. Praktikat më të mira të sigurisë

1. **Vendndodhja e modifikuesit `--json`:** Vendoseni gjithmonë përpara nënkomandës (`omi --json memory list`).
2. **Menaxhimi i kodeve të daljes:** Në skripte automatizimi verifikoni dhe trajtoni gjithmonë kodet nga 1 deri në 5.
3. **Mbrojtja e çelësave:** Mos ngarkoni asnjëherë çelësa API në depo publike kodi. Në mjedise prodhimi dhe CI/CD përdorni ndryshoren e mjedisit `OMI_API_KEY`.
