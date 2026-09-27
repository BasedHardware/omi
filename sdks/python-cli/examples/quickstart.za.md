# Saw cungj vaiq omi-cli (Cuengh)

`omi-cli` dwg mingzlingh youq Omi, mwngz yungh de ndaej vunz yiengh, daihvaq, gongzdan caeuq mbanj. Saw neix caiq Vahcuengh sij, guh duz vunz yungh dienznauj youq gij dungx.

---

## 1. Anz (Installation)

De miz youq PyPI, mingz caiq `omi-cli`. Mwngz anz de youq dienznauj, caeuq mwngz caiq mingzlingh `omi` youq `$PATH`:
```bash
# Banghfaek ndei hoiz: yungh pipx
pipx install omi-cli

# Aek daeuj yungh pip:
pip install omi-cli
```

Yiemh de ndei mbouj, caiq `omi --version` caeuq `omi --help`:
```bash
omi --version
omi --help
```

> **Ndaej roux:** Mingz youq PyPI dwg `omi-cli`. Vunz baenz yungh mingz `omi` laeuz, mingzlingh youq dienznauj dwg `omi`.

---

## 2. Bae dauq (Authentication)

`omi-cli` miz song banghfaek bae dauq: banghfaek it dwg dauq naeuz youq gij ngangq, banghfaek ngeih dwg yungh API key:
```bash
omi auth login
# 1) Naeuz — bae dauq (Google caeuq Apple)
# 2) API key — ndaej key youq app.omi.me
```

### Bae dauq youq naeuz
```bash
# Yungh Google bae dauq
omi auth login --browser

# Yungh Apple bae dauq
omi auth login --browser --provider apple
```

### Bae dauq yungh API key

Youq [app.omi.me](https://app.omi.me) **Developer → API Keys** ndaej API key:
```bash
# Damh key youq profile youq ndeu
omi auth login --api-key omi_dev_zure_gakoa_hemen

# Aek daeuj damh de youq dienznauj:
export OMI_API_KEY="omi_dev_zure_gakoa_hemen"
```

> **Ndaej roux anzen caeuq gij ndeu:**
> * Mwngz yungh `--api-key` youq mingzlingh doengh, vunz baenz roux key youq dienznauj mwngz. Yungh dienznauj boux vunz baenz, caiq banghfaek it (`omi auth login`) aek daeuj yungh `OMI_API_KEY`.
> * Profile youq ndeu miz key laeuz, de youq ndeu, `OMI_API_KEY` youq laeng. Mwngz yungh `OMI_API_KEY`, bae ok (`omi auth logout`) gonq, caeuq caiq profile baenz.

### Yiemh de bae dauq ndaej mbouj

* `omi auth status`: roux profile youq ndeu caeuq mingz youq dienznauj (mbouj ndaej gij ngangq caiq de ndaej).
* `omi auth whoami`: de bae youq gij ngangq youq Omi, yiemh de bae dauq ndaej mbouj.
```bash
omi auth status
omi auth whoami
```

### Bae ok (Logout)

Yungh neix bae ok, key youq dienznauj mbouj miz laeuz:
```bash
omi auth logout
# Yungh OMI_API_KEY laeuz, mbouj caiq de:
unset OMI_API_KEY
```

> **Ndaej roux anzen saw:** Saw youq `~/.omi/config.toml` miz. Youq Unix/Linux, ndei lai caiq: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Mingzlingh (Basic commands)

### Vunz yiengh (Memories)

Yungh de damh vunz yiengh, caeuq ndaej de youq laeng:
```bash
# Vunz yiengh youq ndeu
omi memory list

# Sai vunz yiengh
omi memory create "Vunz ndei saw gij ndeij youq Python" --category work

# Ndaej vunz yiengh it aen
omi memory get <OROITZAPEN_ID>
```

### Daihvaq (Conversations)

Dienznauj Omi damh daihvaq caeuq saw vunz gangj:
```bash
# Haj aen daihvaq youq laeng
omi conversation list --limit 5

# Ndaej it aen daihvaq caeuq saw de
omi conversation get <ELKARRIZKETA_ID> --include-transcript
```

### Gongzdan (Action Items)

Gongzdan youq daihvaq, dienznauj ndaej de youq ndeu:
```bash
# Gongzdan youq ndeu
omi action-item list --open

# Gongzdan neix bae ndaej laeuz
omi action-item complete <ZEREGIN_ID>
```

### Mbanj (Goals)

Roux mbanj youq laeng caeuq de bae ndaej:
```bash
# Mbanj youq ndeu
omi goal list

# Sai mbanj
omi goal create "Raemx ngoenz ngoenz" --type numeric --target 2500 --unit "ml"
```

---

## 4. `--json` caeuq dienznauj (Structured automation and JSON output)

`omi-cli` guh vunz sai youq dienznauj yungh gij ngangq. `--json` ndaej JSON ndei, caiq `jq` roux de:
```bash
# Ndaej vunz yiengh youq JSON, yungh jq
omi --json memory list | jq '.[] | {id, content, category}'

# Ndaej mingz haj aen daihvaq
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Gongzdan youq ndeu
omi --json action-item list --open | jq '.'
```

> **Gij ndeu ndaej roux:**
> `--json` youq ndeu, mwngz fangq de youq ndeu mingzlingh baenz:
> * Ndei: `omi --json memory list`
> * Mbouj ndei: `omi memory list --json`

### Ndaej saw lai lai

De miz saw lai, yungh `--limit` caeuq `--offset`:
```bash
# Ndaej saw it naeuz it naeuz
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
omi --json memory list --limit 25 --offset 25 > memories-page-2.json
```

Mwngz sai saw bae dauq vwenjzien, de damh vwenjzien moq youq dienznauj, aek daeuj gaen de youq ndeu. Gonq caiq saw, yiemh mingzlingh ok ndaej mbouj. Saw youq mbouj ndeij ndaej, mbouj dwg saw mbouj miz. Saw ndaej ok youq ndeu miz saw boux vunz baenz ndaej mbouj roux, ndaej roux anzen.

---

## 5. Code ok (Exit Codes Contract)

`omi-cli` yungh code ok youq ndeu, guh dienznauj yungh. 0 dwg ndei; mbouj dwg 0 dwg youq ndeij.

| Code | Mingz | De dwg cauh |
| :---: | :--- | :--- |
| `0` | **Ndei (`EXIT_OK`)** | Mingzlingh bae ndaej, mbouj miz saw youq ndeij. |
| `1` | **Yungh youq ndeij (`EXIT_USAGE`)** | Mingzlingh mbouj ndei (`UsageError`). |
| `2` | **Bae dauq youq ndeij (`EXIT_AUTH`)** | Mbouj miz key, key ok laeuz, aek daeuj mbouj ndaej bae dauq. |
| `3` | **Gij ngangq youq ndeij (`EXIT_SERVER`)** | Omi youq gij ngangq mbouj ndaej, aek daeuj gij ngangq doenz. |
| `4` | **Caiq lai (`EXIT_RATE_LIMITED`)** | HTTP 429 — youq doenz neix mwngz caiq lai. |
| `5` | **Mbouj ndaej (`EXIT_NOT_FOUND`)** | HTTP 404 — mbouj miz gij neix.

---

## 6. Saw youq dienznauj baenz

Caiq dienznauj yungh, yiemh code ok gonq. Gij dienznauj baenz, banghfaek baenz:

### Bash / Zsh (Linux caeuq macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Ndaej $(jq 'length' /tmp/memories.json) aen vunz yiengh laeuz."
else
    code=$?
    echo "Youq ndeij, ndaej vunz yiengh mbouj ndaej (code: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)
```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Mingzlingh youq ndeij, code: $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Saw damh laeuz."
```

### Windows Command Prompt (`cmd.exe`)
```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Youq ndeij, code: %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Bae ndaej laeuz.
```

---

## 7. Yungh lai profile (Profile management and staging)

`--profile` guh mwngz miz lai profile: profile youq ranz, profile gongh, profile yiemh. Yungh profile yiemh (staging), mwngz sai URL youq ndeu youq profile:

> **Ndaej roux `--api-base`:** `--api-base` dwg banghfaek youq doenz neix, mbouj sai youq saw youq laeng. Mwngz yungh youq laeng, caiq `config set api_base <url>`.
```bash
# Sai URL youq profile yiemh
omi --profile staging config set api_base https://api.staging.omi.me

# Bae dauq youq profile yiemh
omi --profile staging auth login --api-key omi_dev_staging_gakoa

# Caiq mingzlingh youq profile yiemh
omi --profile staging memory list

# Aek daeuj yungh it roeng:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 8. Dienznauj Omi youq ranz (Local Desktop API)

Dienznauj Omi youq ranz mwngz bae ndaej, mwngz caiq de gangj caeuq gij ngangq youq dienznauj, mbouj sai saw bae youq gij ngangq youq baenz. Gonq caiq `omi local status`, ndaej roux URL caeuq token miz laeuz:
```bash
# 1. Sai URL caeuq token youq dienznauj neix:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="your_local_token"

# Aek daeuj damh de youq profile:
# omi local configure --url http://127.0.0.1:47778 --token "your_local_token"

# 2. Roux gij ngangq youq dienznauj neix ndaej mbouj
omi local status

# 3. Youq saw youq ndeu ndaej saw youq dienznauj
omi local search-screen "asteroko bilera" --days 1 --app "Slack"
```

---

## 9. Ndaej roux anzen

1. **`--json` youq gij ndeu:** fangq de youq ndeu mingzlingh baenz (`omi --json memory list`).
2. **Yiemh code ok:** caiq dienznauj yungh, yiemh code 1 daengz 5.
3. **Ndaej roux key:** mbouj sai key bae youq gij ngangq boux vunz roux. Youq dienznauj gongh, caiq `OMI_API_KEY`.
