# មគ្គុទ្ទេសក៍ចាប់ផ្តើមរហ័ស omi-cli (Khmer Quickstart)

> មគ្គុទ្ទេសក៍ជាក់ស្តែងសម្រាប់ធ្វើការជាមួយ Omi ដោយផ្ទាល់ពី terminal — សម្រាប់អ្នកអភិវឌ្ឍន៍ និង AI agent ស្វ័យប្រវត្តិ។

`omi-cli` គឺជា command-line interface ផ្លូវការសម្រាប់ developer API របស់ [Omi](https://omi.me)។ វាអនុញ្ញាតឱ្យអ្នកគ្រប់គ្រងសមាសធាតុស្នូលទាំងបួនរបស់ប្រព័ន្ធតាមរបៀបដែលមានរចនាសម្ព័ន្ធ និងអាចធ្វើស្វ័យប្រវត្តិកម្មបាន៖ ការចងចាំ (memories), ការសន្ទនា (conversations), ចំណុចត្រូវធ្វើ (action items) និងគោលដៅ (goals)។

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **ឯកសារផ្លូវការ:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **កូដប្រភព:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

ឈ្មោះ command, option និងសារបស់កម្មវិធីនៅតែជាភាសាអង់គ្លេស។ មានតែអត្ថបទពន្យល់ក្នុងមគ្គុទ្ទេសក៍នេះប៉ុណ្ណោះដែលជាភាសាខ្មែរ។ README ភាសាអង់គ្លេសគឺជាប្រភពយោងចម្បង។

---

## ១. ការដំឡើង

ដើម្បីជៀសវាងជម្លោះ dependency និងដំណើរការ CLI ក្នុងបរិស្ថានដាច់ដោយឡែក សូមប្រើ `pipx`៖

```bash
# ណែនាំ: ដំឡើងដាច់ដោយឡែកជាមួយ pipx
pipx install omi-cli

# ជម្រើសផ្សេង: ជាមួយ pip ក្នុង Python virtual environment ដែលបានធ្វើឱ្យសកម្ម
pip install omi-cli
```

> **ចំណាំ: ឈ្មោះ package ធៀបនឹងឈ្មោះ command**
> * ឈ្មោះ package នៅលើ PyPI គឺ **`omi-cli`** (ឈ្មោះ `omi` ជារបស់ package មួយផ្សេងដែលមិនពាក់ព័ន្ធ)។
> * command ដែលអ្នកដំណើរការក្នុង terminal គឺគ្រាន់តែ **`omi`**។

ផ្ទៀងផ្ទាត់ថាការដំឡើងដំណើរការ៖

```bash
omi --version
omi --help
```

ប្រសិនបើ terminal រកមិនឃើញ `omi` សូមពិនិត្យថា virtual environment បានធ្វើឱ្យសកម្ម ឬថត (directory) ដែល `pipx` ដាក់ executable មាននៅក្នុង `PATH` របស់អ្នក។

---

## ២. ការផ្ទៀងផ្ទាត់អត្តសញ្ញាណ (Authentication)

`omi-cli` គាំទ្រវិធីសាស្ត្រផ្ទៀងផ្ទាត់ចម្បងពីរ៖

| វិធីសាស្ត្រ | ករណីប្រើប្រាស់ | ឧទាហរណ៍ |
| :--- | :--- | :--- |
| **Developer API key (`omi_dev_*`)** | Script, CI/CD, server គ្មានអេក្រង់, AI agent | `omi auth login --api-key ...` ឬ `OMI_API_KEY` |
| **Browser OAuth (Google/Apple)** | ស្ថានីយការងារមូលដ្ឋាន និងអ្នកអភិវឌ្ឍន៍ | `omi auth login --browser` (Google) / `--provider apple` |

### ការចូលបែបអន្តរកម្ម
ដំណើរការដោយគ្មាន flag ដើម្បីជ្រើសរើសវិធីសាស្ត្របែបអន្តរកម្ម៖

```bash
omi auth login
# 1) Browser — បើក browser សម្រាប់ចូលដោយ Google (ប្រើ `--provider apple` សម្រាប់ Apple)
# 2) API key — បិទភ្ជាប់ API key ពី app.omi.me (ការបញ្ចូលត្រូវបានលាក់)
```

### ចូលដោយផ្ទាល់តាម browser
```bash
# លំនាំដើម: ចូលដោយ Google
omi auth login --browser

# ជម្រើសផ្សេង: ចូលដោយ Apple
omi auth login --browser --provider apple
```

### ការប្រើ developer API key
បង្កើត key នៅ [app.omi.me](https://app.omi.me) ក្រោម **Developer → API Keys**៖

```bash
# រក្សាទុក key ក្នុង local profile ដែលកំពុងសកម្ម
omi auth login --api-key omi_dev_token_ពិតរបស់អ្នក

# ឬកំណត់ជា environment variable (ល្អបំផុតសម្រាប់ container និង CI/CD)
export OMI_API_KEY="omi_dev_token_ពិតរបស់អ្នក"
```

> `OMI_API_KEY` ត្រូវបានប្រើតែនៅពេលដែល profile សកម្មមិនមាន key រក្សាទុកប៉ុណ្ណោះ។ ប្រសិនបើអ្នកបានចូលរួចហើយដោយ `omi auth login` ហើយចង់ឱ្យ environment variable មានប្រសិទ្ធភាព សូមដំណើរការ `omi auth logout` ជាមុនសិន។

### ពិនិត្យស្ថានភាពការផ្ទៀងផ្ទាត់
* `omi auth status`៖ បង្ហាញ profile សកម្ម និងព័ត៌មានសម្ងាត់ដែលបានបិទបាំង (ដំណើរការក្នុងមូលដ្ឋាន/ក្រៅបណ្តាញ; កាលបរិច្ឆេទផុតកំណត់ត្រូវបានអនុវត្តតែចំពោះ OAuth token ប៉ុណ្ណោះ)។
* `omi auth whoami`៖ ផ្ញើសំណើទៅ Omi server ដើម្បីផ្ទៀងផ្ទាត់សុពលភាព (ត្រូវការបណ្តាញ)។

```bash
omi auth status
omi auth whoami
```

ធ្វើឱ្យ OAuth token ថ្មីដោយមិនចាំបាច់ចូលម្តងទៀត៖

```bash
omi auth refresh
```

> `omi auth refresh` ដំណើរការតែសម្រាប់ profile ដែលបានចូលតាម browser (OAuth) ប៉ុណ្ណោះ។ សម្រាប់ profile ដែលផ្អែកលើ API key គ្មានអ្វីត្រូវធ្វើឱ្យថ្មីទេ ហើយ command នឹងបញ្ចប់ដោយសារ «Nothing to refresh» និង exit code `1`។

ចាកចេញ៖
```bash
omi auth logout
# ប្រសិនបើ OMI_API_KEY ត្រូវបានកំណត់ក្នុង environment សូមលុបវាចេញផងដែរ (Bash/Zsh: `unset OMI_API_KEY`)។
```

---

## ៣. Command ស្នូល

### ការចងចាំ (Memories)
ការពិតដែលមានរចនាសម្ព័ន្ធ និងការសង្កេតតាមបរិបទដែល Omi បានរក្សាទុក៖

```bash
# រាយបញ្ជីការចងចាំ
omi memory list

# បង្កើតការចងចាំថ្មីជាមួយប្រភេទ
omi memory create "ចូលចិត្តចម្លើយបច្ចេកទេសខ្លីៗជាមួយឧទាហរណ៍ Python" --category work

# ទាញយកការចងចាំជាក់លាក់តាម ID
omi memory get <MEMORY_ID>
```

### ការសន្ទនា (Conversations)
ការថតសំឡេង, អត្ថបទចម្លង និងការសន្ទនាដែលបានកត់ត្រាដោយឧបករណ៍ Omi៖

```bash
# រាយបញ្ជីការសន្ទនាចុងក្រោយ ៥
omi conversation list --limit 5

# ទាញយកព័ត៌មានលម្អិតនៃការសន្ទនាមួយ រួមទាំងអត្ថបទចម្លងពេញលេញ
omi conversation get <CONVERSATION_ID> --include-transcript
```

### ចំណុចត្រូវធ្វើ (Action Items)
កិច្ចការដែលបានទាញយកដោយស្វ័យប្រវត្តិពីការសន្ទនា៖

```bash
# រាយបញ្ជីចំណុចត្រូវធ្វើដែលនៅបើក
omi action-item list --open

# សម្គាល់ចំណុចត្រូវធ្វើមួយថាបានបញ្ចប់
omi action-item complete <ACTION_ITEM_ID>
```

### គោលដៅ (Goals)
សូចនាករវឌ្ឍនភាព និងគោលដៅរយៈពេលវែង៖

```bash
# រាយបញ្ជីគោលដៅសកម្ម
omi goal list

# បង្កើតគោលដៅជាលេខថ្មី
omi goal create "ផឹកទឹក ២ លីត្រក្នុងមួយថ្ងៃ" --type numeric --target 2 --unit liters

# ធ្វើបច្ចុប្បន្នភាពតម្លៃបច្ចុប្បន្នរបស់គោលដៅ (ID និងតម្លៃថ្មី)
omi goal progress <GOAL_ID> 1.5
```

---

## ៤. ស្វ័យប្រវត្តិកម្មដែលមានរចនាសម្ព័ន្ធ និងលទ្ធផល JSON (`--json`)

`omi-cli` ត្រូវបានបង្កើតឡើងសម្រាប់ស្វ័យប្រវត្តិកម្មក្នុង pipeline និង toolchain។ flag សកល `--json` ត្រឡប់ JSON ស្អាតដែលម៉ាស៊ីនអាចអានបាន៖

```bash
# រាយបញ្ជីការចងចាំជា JSON ហើយច្រោះជាមួយ jq
omi --json memory list | jq '.[] | {id, content, category}'

# ទាញយកចំណងជើងនៃការសន្ទនាចុងក្រោយ
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# មើលចំណុចត្រូវធ្វើដែលនៅបើកទាំងអស់ជា JSON ឆៅ
omi --json action-item list --open | jq '.'
```

> **ច្បាប់វាក្យសម្ព័ន្ធសំខាន់៖**
> `--json` គឺជា **option សកល** ហើយត្រូវដាក់ **មុន** subcommand៖
> * ត្រឹមត្រូវ: `omi --json memory list`
> * ខុស: `omi memory list --json`

### ការបែងចែកទំព័រ (Pagination)
command `list` គាំទ្រ `--limit` និង `--offset`៖

```bash
omi --json memory list --limit 50 --offset 50
```

### នាំចេញទៅឯកសារ
ដើម្បីកុំឱ្យពណ៌ ANSI ឬតួអក្សរត្រួតពិនិត្យចូលក្នុងឯកសារ សូមបញ្ជូន stdout ដោយផ្ទាល់ក្នុង shell៖

```bash
# នាំចេញការចងចាំដោយផ្ទាល់ទៅឯកសារ JSON ស្អាត
omi --json memory list > memories.json
```

---

## ៥. Exit code (Exit Codes Contract)

សម្រាប់ការគ្រប់គ្រងកំហុសដែលអាចទុកចិត្តបានក្នុង CI/CD និង script `omi-cli` អនុវត្តតាមកិច្ចសន្យា exit code ដ៏តឹងរ៉ឹង (សូមមើល `omi_cli/errors.py`)៖

| កូដ | ឈ្មោះ | ការពិពណ៌នា និងឧទាហរណ៍ |
| :---: | :--- | :--- |
| `0` | **ជោគជ័យ (`EXIT_OK`)** | ប្រតិបត្តិការបានបញ្ចប់ដោយគ្មានកំហុស។ |
| `1` | **កំហុសការប្រើប្រាស់ (`EXIT_USAGE`)** | កំហុសផ្ទៀងផ្ទាត់ផ្ទាល់របស់ omi-cli៖ `--browser` និង `--api-key` ដែលមិនអាចប្រើរួមគ្នា, ជម្រើសមិនត្រឹមត្រូវក្នុងការចូលបែបអន្តរកម្ម, ការបញ្ចូលទទេពី stdin ឬ `omi auth refresh` លើ profile API key។ |
| `2` | **កំហុសផ្ទៀងផ្ទាត់ (`EXIT_AUTH`)** | ព័ត៌មានសម្ងាត់បាត់ ឬមិនត្រឹមត្រូវ ឬ session ផុតកំណត់។ ចំណាំ៖ flag មិនស្គាល់ ឬ argument បាត់ក៏ត្រូវបានបដិសេធដោយ Click ខ្លួនឯង ហើយចេញដោយកូដ `2` ដែរ។ |
| `3` | **កំហុស server (`EXIT_SERVER`)** | HTTP 5xx ពី Omi server ឬការដាច់បណ្តាញ។ |
| `4` | **ដែនកំណត់អត្រា (`EXIT_RATE_LIMITED`)** | HTTP 429 — សំណើច្រើនពេកក្នុងរយៈពេលខ្លី។ |
| `5` | **រកមិនឃើញ (`EXIT_NOT_FOUND`)** | HTTP 404 — ធនធានដែលបានស្នើ (ការចងចាំ, ការសន្ទនា, ចំណុចត្រូវធ្វើ) មិនមានទេ។ |

---

## ៦. ឧទាហរណ៍សម្រាប់ shell ផ្សេងៗ

### Bash / Zsh (Linux / macOS)
```bash
# កំណត់ API key សម្រាប់ session នេះ
export OMI_API_KEY="omi_dev_token_ពិតរបស់អ្នក"

# ដំណើរការ command ហើយពិនិត្យ exit code
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "កំហុសក្នុងការទាញយកការចងចាំពី Omi។" >&2
fi
```

### PowerShell (Windows)
```powershell
# កំណត់ environment variable ក្នុង PowerShell
$env:OMI_API_KEY = "omi_dev_token_ពិតរបស់អ្នក"

# បម្លែងលទ្ធផល JSON ទៅជា PowerShell object ដោយផ្ទាល់
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# ពិនិត្យកំហុសជាមួយ $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "command Omi បរាជ័យដោយ exit code $LASTEXITCODE។"
}
```

---

## ៧. ការរួមបញ្ចូល Local Desktop API (Omi Desktop)

នៅពេល Omi Desktop កំពុងដំណើរការលើម៉ាស៊ីនរបស់អ្នក (port លំនាំដើម 47778) អ្នកអាចធ្វើការដោយផ្ទាល់ជាមួយបរិបទមូលដ្ឋានដោយមិនចាំបាច់ឆ្លងកាត់ cloud៖

```bash
# កំណត់រចនាសម្ព័ន្ធការតភ្ជាប់ local API (ប្រើ environment variable ដើម្បីការពារ token)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "បញ្ចូល Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# បញ្ជាក់ស្ថានភាពការតភ្ជាប់មូលដ្ឋាន
omi --json local status

# ស្វែងរកក្នុងប្រវត្តិអេក្រង់មូលដ្ឋាន
omi --json local search-screen "របាយការណ៍ប្រចាំត្រីមាស" --days 7 --app Safari
```

ជំនួសឱ្យ environment variable អ្នកអាចរក្សាទុកការកំណត់លើ profile៖ `omi local configure --url http://127.0.0.1:47778 --token ...`។

---

## ៨. ការគ្រប់គ្រង profile ច្រើន (Profiles)

ប្រើ `--profile` ដើម្បីប្តូររវាងគណនីផ្ទាល់ខ្លួន, profile ការងារ ឬបរិស្ថានសាកល្បងដោយរលូន។ ការកំណត់ត្រូវបានរក្សាទុកក្នុង `~/.omi/config.toml`។ លំដាប់អាទិភាព៖ flag `--profile` បន្ទាប់មក environment variable `OMI_PROFILE` ហើយចុងក្រោយ profile `default`។

```bash
# បង្កើត និងចូល profile ផ្ទាល់ខ្លួន
omi --profile personal auth login

# បង្កើត និងចូល profile ការងារ
omi --profile work auth login

# ដំណើរការ command ជាមួយ profile ជាក់លាក់
omi --profile work memory list

# ជ្រើសរើស profile តាម environment variable
export OMI_PROFILE=work
omi memory list

# ប្រើ endpoint ផ្ទាល់ខ្លួនសម្រាប់ការសាកល្បង
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## ៩. គោលការណ៍ណែនាំសុវត្ថិភាព និងការអនុវត្តល្អបំផុត

* **កុំសរសេរ key ក្នុងកូដ៖** កុំ commit API key (`omi_dev_*`) ទៅ Git repository ដាច់ខាត។ ប្រើឯកសារ `.env` ដែលបានបន្ថែមទៅ `.gitignore` ឬកម្មវិធីគ្រប់គ្រងអាថ៌កំបាំងដែលមានសុវត្ថិភាព។
* **ការពារប្រវត្តិ shell៖** នៅលើ server ដែលចែករំលែក កុំបញ្ជូន key ជា argument ក្នុង command line ដោយផ្ទាល់; ប្រើការចូលបែបអន្តរកម្ម ឬ `OMI_API_KEY`។
* **រឹតបន្តឹងសិទ្ធិថត៖** នៅលើ Unix/macOS សូមធានាថាថតកំណត់រចនាសម្ព័ន្ធមានសិទ្ធិកំណត់៖
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **សម្អាត session៖** នៅពេលរុះរើបរិស្ថានបណ្តោះអាសន្ន សូមចាំលុប environment variable៖
  ```bash
  unset OMI_API_KEY
  ```
