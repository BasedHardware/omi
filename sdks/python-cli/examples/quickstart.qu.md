# Utqaylla Qallariy Yanapakuy: omi-cli (Runa Simi)

`omi-cli` nisqaqa Omi llika ukhupi llank'anapaq kamachina siq'i chawpinmi (CLI): yuyaykunata (memories), rimanakuykunata (conversations), ruranakunata (action items) chaymanta munasqakunata (goals) kamachiypaq. Kay qillqaqa Runa Simipim qillqasqa kachkan, runakunapaq, llank'aqkunapaq chaymanta AI ruwaqkunapaqpas.

---

## 1. Churanakuy (Installation)

Kay p'anqaqa PyPI nisqapi `omi-cli` sutiyuqmi mast'arisqa kachkan. Churasqa kaptinqa, `omi` kamachinaqa `$PATH` k'itiykipi llank'anqa:

```bash
# Pipx nisqawan sapaqchasqa pachapi churay (aswan allin):
pipx install omi-cli

# Icha sapaq pip nisqawan:
pip install omi-cli
```

Churasqa kasqanta qhaway bertsiyoninta chaymanta yanapakuyninta tapuspa:

```bash
omi --version
omi --help
```

> **Yuyaychay:** PyPI paquete sutinqa `omi-cli` nisqam (huk paquete `omi` sutiyuq kasqanrayku), ichaqa terminalpi kamachinaqa sapa kuti `omi` nisqallam.

---

## 2. Chiqapchay (Authentication)

`omi-cli` yanapakuyqa web wamp'uq (browser) nisqawanpas utaq llank'achiqpa API kichanawanpas (API key) yaykuyta saqillanmi:

```bash
omi auth login
# 1) Browser — Wamp'uqwan yaykuy (Google icha Apple)
# 2) API key — app.omi.me panilmanta kichana churasqa
```

### Web wamp'uqwan yaykuy (Browser login)

```bash
# Google yupaywan yaykuy (ñawpaq churasqa)
omi auth login --browser

# Apple yupaywan yaykuy
omi auth login --browser --provider apple
```

### API kichanawan yaykuy (API Key login)

Huk API kichanata [app.omi.me](https://app.omi.me) kamachiq p'anqapi paqarichiy **Developer → API Keys** nisqapi:

```bash
# Kichanata kunan kaq profilpi waqaychay:
omi auth login --api-key omi_dev_kichanayki_kaypi

# Icha pachapa kaqnintinpi churay (Docker chaymanta CI/CD ruwaykunapaq allin):
export OMI_API_KEY="omi_dev_kichanayki_kaypi"
```

> **Amachaypaq yuyaychay:**
> * `--api-key` nisqata chiqalla terminalpi qillqayqa kitiqpa qillqasqanpi (`shell history`) qhipakunman. Lliwpa llamk'anan antañiqiqkunapiqa interactive nisqata (`omi auth login`) icha `OMI_API_KEY` nisqata llamk'achiy.
> * Profilpi waqaychasqa kichanaqa `OMI_API_KEY` nisqamanta ñawpaqman churasqam. `OMI_API_KEY` llamk'achiyta munaspasqa, ñawpaqta llikiy `omi auth logout` nisqawan icha musuq profilta llamk'achiy.

### Yaykuy kasqanta qhaway

* `omi auth status`: Kunan profilta chaymanta pakisqa yaykunata qhawachin (mana internet nisqawanpas llank'anmi).
* `omi auth whoami`: Omi sirwiqkunaman willakuyta kachan chiqaptapuni qhawanapaq.

```bash
omi auth status
omi auth whoami
```

### Llikiy (Logout)

Antañiqiqpi waqaychasqa willakuykunata pichanapaq:

```bash
omi auth logout
# OMI_API_KEY nisqata llamk'achirqanki chayqa, qichuy:
unset OMI_API_KEY
```

> **Waqaychanakuna qhaway:** Tukuy allichaykunaqa `~/.omi/config.toml` k'itipim waqaychakun. Unix/Linux llikakunapiqa, amachaykuna churayta amataq qunqaychu: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Qallariynin kamachinakuna

### Yuyaykuna (Memories)

Unay pachapaq yuyaykuna, riqsisqakuna chaymanta qillqasqakuna:

```bash
# Lliw yuyaykunata rikuy
omi memory list

# Musuq yuyayta paqarichiy
omi memory create "Ruraqqa Python yachaykunawan allin kutichiykunata munan" --category work

# Huk yuyayta kikin yupayninwan qhaway
omi memory get <YUYAY_ID>
```

### Rimanakuykuna (Conversations)

Omi llikamanta kunkakuna chaymanta qillqasqakuna:

```bash
# Qhipa 5 rimanakuykunata rikuy
omi conversation list --limit 5

# Rimanakuyta tukuy qillqasqanpiwan (transcript) huqariy
omi conversation get <RIMANAKUY_ID> --include-transcript
```

### Ruranakuna (Action Items)

Rimanakuykunamanta kikinmanta lluqsimuq ruranakuna:

```bash
# Kichasqa kaq ruranakunata rikuy
omi action-item list --open

# Huk ruranata tukusqa nispa markay
omi action-item complete <RURANA_ID>
```

### Munasqakuna (Goals)

Hatun munasqakuna chaymanta ñawpaqman puriy qhaway:

```bash
# Kunan purichkaq munasqakunata rikuy
omi goal list

# Yupayniyuq musuq munasqata paqarichiy
omi goal create "Sapa p'unchaw yaku upyay" --type numeric --target 2500 --unit "ml"
```

---

## 4. Allichasqa ruwaykuna chaymanta JSON lliklla (`--json`)

`omi-cli` nisqaqa scriptkunapi chaymanta AI ruwaqkunapi (agents) llamk'anapaqmi rurasqa. `--json` hatun unanchachaqa llimp'i JSON willayta qun, `jq` nisqawan allin t'aqwinapaq:

```bash
# Yuyaykunata JSON nisqapi hurquy chaymanta jq nisqawan akllay
omi --json memory list | jq '.[] | {id, content, category}'

# Qhipa 5 rimanakuykunap umalliqninta hurquy
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Kichasqa ruranakunata qhaway
omi --json action-item list --open | jq '.'
```

> **Hatun kamachiy:**
> `--json` nisqaqa tukuy llank'anapaq hatun unanchacham (global flag), chaymi sapa kuti uran-kamachinapa **ñawpaqinpi** churasqa kanan tiyan:
> * Allin: `omi --json memory list`
> * Pantasqa: `omi memory list --json`

### P'anqachay chaymanta willakuykuna waqaychay

Aswan achka willaykunapaqqa `--limit` chaymanta `--offset` nisqata llamk'achiy:

```bash
# Willakuykunata p'anqanpa p'anqan hurquy
omi --json memory list --limit 25 --offset 0 > yuyaykuna-panqa-1.json
omi --json memory list --limit 25 --offset 25 > yuyaykuna-panqa-2.json
```

Huk qillqaman churaspaqa antañiqiqpi musuqmanta qillqakunqa. Manaraq llamk'achkaspa llikina kódikuta allinta qhaway. Pantay willakuykunaqa `stderr` nisqamanmi rin, chayrayku ch'usaq qillqaqa manam pantay mana kasqantachu nin. Lluqsisqa willaykunaqa pakasqa willaykunata apanmanmi — amachasqata waqaychay.

---

## 5. Lluqsinapaq kódikukuna (Exit Codes Contract)

`omi-cli` nisqaqa sut'i kódikukunatam qatin automatizacionkunapi allin kananpaq (`omi_cli/errors.py` nisqaman hina):

| Kódiku | Suti | Imata nin chaymanta sut'inchay |
| :---: | :--- | :--- |
| `0` | **Allinlla (`EXIT_OK`)** | Kamachinaqa allinta mana pantaspa tukukun. |
| `1` | **Llamk'achiypi pantay (`EXIT_USAGE`)** | Llamk'anapa pantaynin (`UsageError`, ahinataq `--browser` hinallataq `--api-key` kuskalla churay). |
| `2` | **Chiqapchay pantay / T'aqwiy pantay (`EXIT_AUTH`)** | Kichana mana kanchu, puchukasqa utaq mana saqisqachu. Click/Typer nisqapa pantayninkunapas (mana riqsisqa unanchachakuna, mana allin yupaykuna) 2 kódikuta kutichillantaqmi. |
| `3` | **Sirwiq icha llika pantay (`EXIT_SERVER`)** | Omi sirwiqmanta HTTP 5xx kutichiy utaq llikapi t'inkinakuy p'akikuy. |
| `4` | **Mañakuykuna yallisqa (`EXIT_RATE_LIMITED`)** | HTTP 429 kutichiy — pisi pachallapi nisyu achka mañakuykuna kachasqa. |
| `5` | **Mana tarisqachu (`EXIT_NOT_FOUND`)** | HTTP 404 kutichiy — mañakusqa kaqqa manam kanchu. |

---

## 6. Sapaq terminal pachakunapaq rikch'anachiykuna

### Bash / Zsh (Linux chaymanta macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/yuyaykuna.json; then
    echo "Allinlla hurqusqa: $(jq 'length' /tmp/yuyaykuna.json) yuyaykuna."
else
    code=$?
    echo "Pantay yuyaykunata hurquypi (lluqsinapaq kódiku: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\yuyaykuna.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Kamachinaqa pantasqa tukukun: $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Willaykuna allin waqaychasqa."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\yuyaykuna.json"
if %ERRORLEVEL% NEQ 0 (
    echo Pantaymi karqan lluqsinapaq kódikuwan: %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Ruwayqa allinmi tukukun.
```

---

## 7. Kikin profilkuna chaymanta llank'ana pacha (Profiles & Staging)

`--profile` unanchachaqa sapaq allichaykunata waqaychayta saqin (ahinataq llamk'anapaq, kikinpaq icha pruebas nisqapaq). Staging pruebakunapaqqa, API base URL nisqata profilpi churayta atinki:

```bash
# Staging profilpaq API nisqata wiñaypaq churay
omi --profile staging config set api_base https://api.staging.omi.me

# Staging profilpi yaykuy
omi --profile staging auth login --api-key omi_dev_staging_kichana

# Staging profilpi kamachinakunata purichiy
omi --profile staging memory list

# Icha huk kutillapaq kamachinapi churay:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Yuyaychay `--api-base` nisqamanta:** `--api-base` unanchachaqa chay kamachinallapaqmi llank'an, manam kikinmanta waqaychakunchu. Wiñaypaq waqaychanaykipaqqa `config set api_base <url>` nisqata llamk'achiy.

---

## 8. Desktop ukun API nisqawan tinkichiy (Local Desktop API)

Omi Desktop nisqa kikin antañiqiqpi llamk'achkaptinqa, chiqalla kiti sirwiqwan willanakuyta atinki mana llikaman willaykunata kachaspa. Manaraq `omi local status` nisqata purichkaspa, k'iti tiyayninta chaymanta tokenninta churay:

```bash
# 1. K'iti tiyayta (47778 puerto) chaymanta tokenta churay:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="kiti_tokenniyki"

# Icha profilpi wiñaypaq waqaychay:
# omi local configure --url http://127.0.0.1:47778 --token "kiti_tokenniyki"

# 2. K'iti sirwiypa kayninta qhaway
omi local status

# 3. Pantallapa kawsayninpi machkay
omi local search-screen "sapa simana huñunakuy" --days 1 --app "Slack"
```

---

## 9. Amachay chaymanta allin yachaykuna

1. **`--json` unanchachapa k'itin:** Sapa kuti uran-kamachinapa ñawpaqinpi churay (`omi --json memory list`).
2. **Lluqsinapaq kódikukunata kamachiy:** Scriptkunapiqa 1-manta 5-kama kódikukunata allinta qhaway chaymanta allichay.
3. **Kichanakunata amachay:** Ama hayk'appas API kichanakunata lliwpaq GitHub k'itikunaman churaychu. CI/CD nisqapaqqa `OMI_API_KEY` nisqata llamk'achiy.
