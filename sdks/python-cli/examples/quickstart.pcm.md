# Kwik-Start Guide: omi-cli (Naija Pidgin)

`omi-cli` na di official command-line interface (CLI) wey pesin take take enta Omi ecosystem: e dey give access to memories, conversations, action items and goals. Dis guide na fully Naija Pidgin, for automation environments, terminal users and developers.

---

## 1. How to Install Am (Installation)

Di package dey for PyPI repository wit di name `omi-cli`. Afta you install am, di `omi` command go dey available for your `$PATH`:
```bash
# Di way wey dem recommend pass: isolated environment wit pipx
pipx install omi-cli

# Or wit ordinary pip:
pip install omi-cli
```

Check say di installation work by check di version and di help message:
```bash
omi --version
omi --help
```

> **Note:** Di name of di PyPI package na `omi-cli` (na because anoda package don already carry di ordinary `omi` name), but di terminal command na `omi` everytime.

---

## 2. How to take Login (Authentication)

`omi-cli` dey support both interactive browser login and developer API keys:
```bash
omi auth login
# 1) Browser — login wit browser (Google or Apple)
# 2) API key — paste di developer key from app.omi.me panel
```

### Login wit Browser
```bash
# Login wit Google account (na di default)
omi auth login --browser

# Login wit Apple account
omi auth login --browser --provider apple
```

### Login wit Developer API Key

Create API key for [app.omi.me](https://app.omi.me) dashboard inside **Developer → API Keys**:
```bash
# For save di key inside di active profile wey dey now
omi auth login --api-key omi_dev_zure_gakoa_hemen

# Or set am as environment variable (na di one dem recommend for Docker and CI/CD):
export OMI_API_KEY="omi_dev_zure_gakoa_hemen"
```

> **Security and priority note:**
> * If you take `--api-key` put for command-line direct, di key go show for terminal history (`shell history`) and system process list. For shared machine, take di interactive mode (`omi auth login`) or di `OMI_API_KEY` environment variable.
> * If di active profile don already save key for config, e get priority pass environment variable. To take `OMI_API_KEY`, logout first wit `omi auth logout` or take new profile.

### Check Session Status

* `omi auth status`: e dey show di active profile and di masked identifier wey dey saved locally (e dey work offline).
* `omi auth whoami`: e dey send network request go Omi servers to check say di session still valid.
```bash
omi auth status
omi auth whoami
```

### Logout

To delete di credentials wey dey saved locally:
```bash
omi auth logout
# If you take OMI_API_KEY environment variable, remove am:
unset OMI_API_KEY
```

> **File security note:** Di config dey saved for `~/.omi/config.toml` file. For Unix/Linux systems, na better make you restrict di permissions: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Basic Commands

### Memories (Memories)

For store and search long-term context notes, events and notes:
```bash
# List of di memories wey you don save
omi memory list

# For create new memory
omi memory create "User prefer sharp-sharp technical answers wit Python examples" --category work

# For take one particular memory wit e identifier
omi memory get <OROITZAPEN_ID>
```

### Conversations (Conversations)

Audio recordings and text transcripts from Omi devices:
```bash
# List of di last 5 conversations
omi conversation list --limit 5

# For take one conversation wit e full transcript
omi conversation get <ELKARRIZKETA_ID> --include-transcript
```

### Action Items and Tasks (Action Items)

Tasks and actions wey dem detect automatically inside conversations:
```bash
# List of tasks wey still open
omi action-item list --open

# For mark task say e don complete
omi action-item complete <ZEREGIN_ID>
```

### Goals (Goals)

For track long-term goals and progress:
```bash
# List of goals wey dey active
omi goal list

# For create new numeric goal (dem dey give di title as positional argument)
omi goal create "How much water I drink daily" --type numeric --target 2500 --unit "ml"
```

---

## 4. Structured Automation and JSON Output (`--json`)

`omi-cli` dem take design am specially for inside scripts and automated AI flows. Di global `--json` flag dey give clean JSON output, wey perfect for process wit tools like `jq`:
```bash
# Take memories for JSON format come filter dem wit jq
omi --json memory list | jq '.[] | {id, content, category}'

# Comot di titles of di last 5 conversations
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# List of tasks wey still open
omi --json action-item list --open | jq '.'
```

> **Main syntax rule:**
> Di `--json` option na global and you must always put am **before** di subcommand:
> * Correct: `omi --json memory list`
> * Wrong: `omi memory list --json`

### Pagination and Data Export

If you dey work wit plenty data, take `--limit` and `--offset` parameters:
```bash
# For download data page by page
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
omi --json memory list --limit 25 --offset 25 > memories-page-2.json
```

If you redirect go file, e go create or overwrite local file. Always check di command exit code before you process data. Error messages dey go standard error (`stderr`), so empty file no mean say data no dey. Exported files fit contain confidential data — protect dem based on your security rules.

---

## 5. Exit Codes (Exit Codes Contract)

`omi-cli` dey take stable contract of exit codes, wey dem take design for automation and AI agents. Zero (0) mean say success; any number wey no be zero mean say error wey get specific meaning.

| Code | Name | Meaning and description |
| :---: | :--- | :--- |
| `0` | **Success (`EXIT_OK`)** | Di command run witout error. |
| `1` | **Usage / app validation error (`EXIT_USAGE`)** | App-level validation error (`UsageError`, for example `--browser` and `--api-key` wey no dey compatible dem take put dem togeda). |
| `2` | **Auth / parse error (`EXIT_AUTH`)** | Credentials no dey, di key don expire or permission no reach. Click/Typer syntax errors and invalid option values sef dey return code 2. |
| `3` | **Server or network error (`EXIT_SERVER`)** | Omi server HTTP 5xx response or network connection cut. |
| `4` | **Rate limit don pass (`EXIT_RATE_LIMITED`)** | HTTP 429 response — dem don send too many requests inside short time. |
| `5` | **Resource no dey (`EXIT_NOT_FOUND`)** | HTTP 404 response — di resource wey dem request no dey.

---

## 6. Examples for Different Terminal Environments

For automation scripts, na better make you always check di exit code before you process any data. Di exact syntax dey depend on di terminal wey you dey take:

### Bash / Zsh (Linux and macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Successfully retrieve $(jq 'length' /tmp/memories.json) memories."
else
    code=$?
    echo "Error dey for to retrieve memories (exit code: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)
```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Di command fail wit exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Data don save well-well."
```

### Windows Command Prompt (`cmd.exe`)
```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Error don happen wit exit code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Everitin don complete well.
```

---

## 7. Profile Management and Staging Environment (Staging)

`--profile` dey let you maintain different independent configs (e.g. personal, work or testing). For staging environments, you fit set di base URL permanently inside di profile:

> **Important note about di `--api-base` option:** Di `--api-base` flag na only temporary override for dat particular command and dem no dey save am automatically for config. For permanent use, take `config set api_base <url>`.
```bash
# For set di base URL permanently for di staging profile
omi --profile staging config set api_base https://api.staging.omi.me

# Login inside di staging test profile
omi --profile staging auth login --api-key omi_dev_staging_gakoa

# For run commands inside di staging profile (e don already point go staging environment)
omi --profile staging memory list

# Or override am temporarily for only one command:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 8. Integration wit Local Desktop API (Local Desktop API)

If di Omi Desktop app dey run for di same computer, you fit take communicate directly wit di local server without sending data go cloud. Before you run `omi local status` or searches, make sure say di address and security token don set:
```bash
# 1. For set di local address (default port na 47778) and token:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="your_local_token"

# Or save am permanently inside di profile:
# omi local configure --url http://127.0.0.1:47778 --token "your_local_token"

# 2. For check di local service status (e need di parameters wey don set before)
omi local status

# 3. For search screen history wit query and app
omi local search-screen "asteroko bilera" --days 1 --app "Slack"
```

---

## 9. Security and Best Practices

1. **`--json` flag position:** Always put am before di subcommand (`omi --json memory list`).
2. **Handle exit codes:** For automation scripts, always check and handle codes 1 to 5.
3. **Protect credentials:** Neva upload API keys go public code repos. For production and CI/CD environments always take di `OMI_API_KEY` variable.
