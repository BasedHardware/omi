# Gabay sa Mabilis na Pagsisimula sa omi-cli (Filipino Quickstart)

> Praktikal na gabay para sa direktang pakikipag-ugnayan sa Omi mula sa iyong terminal — dinisenyo para sa mga developer at autonomous AI agents.

Ang `omi-cli` ay ang opisyal na command-line interface para sa [Omi](https://omi.me) developer API. Nagbibigay-daan ito upang pamahalaan ang apat na pangunahing mapagkukunan (core resources) ng Omi: mga alaala (memories), pag-uusap (conversations), gawain (action items), at mga layunin (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Opisyal na Dokumentasyon:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Source Code:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

> **Paalala:** Ang opisyal na [README sa Ingles](../README.md) ang nananatiling pangunahing pinagmumulan ng katotohanan (source of truth). Ang mga pangalan ng utos at CLI flags ay nananatili sa Ingles; tanging ang mga paliwanag ang isinalin sa Filipino.

---

## 1. Pag-install

Inirerekomenda ang paggamit ng `pipx` upang maiwasan ang mga salungatan sa dependency ng system at patakbuhin ang CLI sa isang nakahiwalay na kapaligiran (isolated environment):

```bash
# Inirerekomenda: Nakahiwalay na pag-install gamit ang pipx
pipx install omi-cli

# O alternatibong pag-install gamit ang karaniwang pip sa loob ng virtual environment
python -m pip install omi-cli
```

> **Mahalagang Pagkakaiba: Pangalan ng Package vs. Pangalan ng Utos**
> * Ang pangalan ng package sa PyPI ay **`omi-cli`** (ang payak na pangalang `omi` ay pagmamay-ari ng ibang package).
> * Ang executable na utos sa terminal ay diretsong **`omi`**.

Tiyaking maayos ang pagkakainstal sa pamamagitan ng pagsuri sa bersyon at tulong:

```bash
omi --version
omi --help
```

Kung hindi mahanap ng terminal ang `omi`, tiyaking aktibo ang iyong virtual environment o nasa iyong `$PATH` ang bin directory ng `pipx`.

---

## 2. Pagpapatunay (Authentication)

Sinusuportahan ng `omi-cli` ang dalawang pangunahing paraan ng pagpapatunay:

| Paraan | Paggamit | Halimbawang Utos |
| :--- | :--- | :--- |
| **Developer API Key (`omi_dev_*`)** | Automation, CI/CD, headless servers, at AI agents | `omi auth login --api-key ...` o `OMI_API_KEY` |
| **Browser OAuth (Google/Apple)** | Personal na computer at mga developer | `omi auth login --browser` (Google) / `--provider apple` |

### Interactive na Pag-login
Kapag pinatakbo nang walang karagdagang flag, bibigyan ka ng pagpipilian:

```bash
omi auth login
# 1) Browser — Mag-sign in gamit ang browser (Google bilang default; gamitin ang `--provider apple` para sa Apple)
# 2) API key — I-paste ang API key mula sa app.omi.me
```

### Direktang Pag-login sa Browser
```bash
# Default na Google login
omi auth login --browser

# Alternatibong Apple ID login
omi auth login --browser --provider apple
```

### Paggamit ng Developer API Key
Gumawa ng API key sa [app.omi.me](https://app.omi.me) sa ilalim ng **Developer → API Keys**:

```bash
# I-save sa lokal na profile gamit ang command
omi auth login --api-key omi_dev_iyong_key_dito

# O itakda bilang environment variable (pinakamainam para sa mga container at CI/CD)
# Paalala: Kung may nakaimbak nang key sa aktibong profile, mag-logout muna: `omi auth logout`
export OMI_API_KEY="omi_dev_iyong_key_dito"
```

### Pagsusuri sa Katayuan ng Pagpapatunay
* `omi auth status`: Ipinapakita ang aktibong lokal na profile at nakatagong credential; ang petsa ng pag-expire ay ipinapakita lamang para sa mga profile ng OAuth (gumagana nang offline).
* `omi auth whoami`: Nagpapadala ng authenticated request sa Omi API upang tiyaking gumagana ang token (nangangailangan ng koneksyon sa internet).

```bash
omi auth status
omi auth whoami
```

Pag-logout:
```bash
omi auth logout
# Kung naka-export ang OMI_API_KEY sa kapaligiran, alisin din ito sa session:
unset OMI_API_KEY
```

Ang lokal na configuration ay nakaimbak sa `~/.omi/config.toml` bilang default. Huwag ibahagi ang file na ito dahil maaaring naglalaman ito ng iyong mga lihim na credential.

---

## 3. Pangunahing mga Utos

### Mga Alaala (Memories)
Mga atomikong kaalaman at kontekstong naitala ng Omi:

```bash
# Ilista ang pinakabagong mga alaala
omi memory list --limit 5

# Gumawa ng bagong alaala
omi memory create "Mas gusto ang maikli at teknikal na sagot na may Python examples" --category work

# Kunin ang detalye ng isang partikular na alaala
omi memory get <MEMORY_ID>
```

### Mga Pag-uusap (Conversations)
Naitalang audio transcripts at kasaysayan ng diyalogo:

```bash
# Ilista ang huling 5 pag-uusap
omi conversation list --limit 5

# Kunin ang detalye ng pag-uusap kasama ang buong transcript
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Mga Gawain at Aksyon (Action Items)
Mga awtomatikong nahalaw na gawain mula sa mga pag-uusap:

```bash
# Ilista ang mga bukas na gawain
omi action-item list --open

# Markahan bilang tapos ang isang gawain
omi action-item complete <ACTION_ITEM_ID>
```

### Mga Layunin (Goals)
Mga sinusubaybayang sukatan at pangmatagalang target:

```bash
# Ilista ang mga aktibong layunin
omi goal list

# Gumawa ng bagong numerikal na layunin
omi goal create "Uminom ng 2L na tubig araw-araw" --type numeric --target 2 --unit liters
```

> **Tip:** Ang walang laman na listahan ay karaniwang nangangahulugang walang tugmang tala. Gamitin ang `--help` sa bawat utos upang makita ang mga magagamit na filter (hal. `omi memory list --help`).

---

## 4. Naka-istrukturang Automation at JSON Output (`--json`)

Ang `omi-cli` ay dinisenyo para sa madaling integrasyon sa mga script at pipeline ng automation. Ibalik ang format sa wastong JSON gamit ang `--json` flag:

```bash
# Ilista ang mga alaala bilang JSON at salain gamit ang jq
omi --json memory list | jq '.[] | {id, content, category}'

# Kunin ang mga pamagat ng pinakabagong pag-uusap
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Tingnan ang mga bukas na gawain sa raw JSON format
omi --json action-item list --open | jq '.'
```

> **Kritikal na Patakaran sa Syntax:**
> Ang `--json` flag ay isang **global option** at kailangang ilagay **bago** ang subcommand:
> * **Wasto:** `omi --json memory list`
> * **Mali:** `omi memory list --json`

### Pag-export sa File
Maaari mong i-redirect ang JSON output sa isang lokal na file:

```bash
omi --json memory list --limit 25 --offset 0 > mga-alaala-pahina-1.json
```

Palaging suriin ang exit code ng utos bago gamitin ang na-export na file. Ang mga mensahe ng error ay ipinapadala sa standard error (stderr). Dahil maaaring maglaman ang file ng personal na impormasyon, panatilihin itong pribado.

---

## 5. Mga Exit Code (Exit Codes Contract)

Maaasahang pagsusuri ng error para sa mga shell script at CI/CD workflows:

| Exit Code | Pangalan | Kahulugan at Aksyon |
| :---: | :--- | :--- |
| `0` | **`EXIT_OK` (Tagumpay)** | Matagumpay na natapos ang operasyon nang walang error. |
| `1` | **`EXIT_USAGE` (Maling Paggamit / Validation)** | Hindi wastong mga value, maling flag, o nagtutunggaling options (hal. `--browser` kasabay ng `--api-key`). |
| `2` | **`EXIT_AUTH` (Authentication / Pahintulot)** | Walang valid na credentials, expired na token, o hindi sapat ang scope/pahintulot ng API key. Patakbuhin ang `omi auth login` o suriin ang key. |
| `3` | **`EXIT_SERVER` (Error sa Server / Koneksyon)** | HTTP 5xx server error o pagkabigo sa koneksyon/network sa transport layer. Subukang muli o tingnan ang status.omi.me. |
| `4` | **`EXIT_RATE_LIMITED` (Nalimitahan ang Bilis / Rate Limited)** | HTTP 429 response — labis na mga kahilingan sa loob ng takdang oras. Maghintay bago magpadala muli ng mga request. |
| `5` | **`EXIT_NOT_FOUND` (Hindi Nahanap)** | HTTP 404 response — ang hiniling na ID o resource ay hindi umiiral. |

---

## 6. Mga Halimbawa sa Iba't Ibang Shell

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_iyong_key_dito"

omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Nagkaroon ng error sa pagkuha ng mga alaala mula sa Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_iyong_key_dito"

# I-convert ang JSON output diretso sa PowerShell object
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Pagsusuri ng error gamit ang $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Nabigo ang omi command na may exit code $LASTEXITCODE."
}
```

---

## 7. Lokal na Desktop API (Omi Desktop)

Kung tumatakbo ang Omi Desktop app sa iyong computer, maaari mong suriin ang lokal na konteksto at kasaysayan ng screen nang hindi dumadaan sa cloud:

```bash
# I-configure ang lokal na endpoint
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Suriin ang katayuan ng lokal na koneksyon
omi --json local status

# Maghanap sa visual timeline ng screen
omi --json local search-screen "Project Update" --days 7 --app Safari
```

---

## 8. Pamamahala ng Maramihang Profile (Profiles)

Gamitin ang `--profile` flag upang magpalipat-lipat sa pagitan ng personal, trabaho, o testing accounts. Naka-save ang mga profile sa `~/.omi/config.toml`:

```bash
# Gumawa ng personal na profile at mag-login
omi --profile personal auth login

# Gumawa ng work profile at mag-login
omi --profile work auth login

# Magpatakbo ng utos gamit ang partikular na profile
omi --profile work memory list

# Magpatakbo laban sa pasadyang staging API endpoint
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Seguridad at Mahahalagang Tagubilin

* **Huwag I-commit ang API Keys:** Huwag kailanman i-save o i-commit ang iyong mga API key sa pampublikong Git repositories. Gamitin ang `.gitignore` at environment variables.
* **Kasaysayan ng Shell:** Iwasang ipasa ang mga API key bilang raw command arguments sa mga shared machine; gamitin ang interactive login o `export OMI_API_KEY`.
* **Proteksyon ng Direktoryo:** Sa mga Unix-like system, higpitan ang permissions ng `~/.omi/` folder (`chmod 700 ~/.omi`).
