# 快速指南：omi-cli (閩南語)

`omi-cli` 是 Omi 生態系統的官方命令列介面（CLI）：會使存取 memories（記持）、conversations（對話）、action items（待辦）佮 goals（目標）。這篇指南攏用閩南語寫，專門予自動化環境、終端使用者佮開發者看。

---

## 1. 安裝 (Installation)

這个包佇 PyPI 倉庫用 `omi-cli` 這个名發布。安裝好了後，`omi` 命令就會佇你的 `$PATH` 裡面出現：
```bash
# 推薦的方法：用 pipx 的隔離環境
pipx install omi-cli

# 或者用普通的 pip：
pip install omi-cli
```

用檢查版本佮幫助訊息來確認安裝成功：
```bash
omi --version
omi --help
```

> **注意：** PyPI 包的名是 `omi-cli`（因為另外一个包已經用掉光个 `omi` 這个名），毋過終端命令永遠是 `omi`。

---

## 2. 認證 (Authentication)

`omi-cli` 既支持瀏覽器的互動式登入，也支持開發者 API 金鑰：
```bash
omi auth login
# 1) 瀏覽器——用瀏覽器登入（Google 或者 Apple）
# 2) API 金鑰——佇 app.omi.me 面板貼上開發者金鑰
```

### 用瀏覽器登入
```bash
# 用 Google 口座登入（預設）
omi auth login --browser

# 用 Apple 口座登入
omi auth login --browser --provider apple
```

### 用開發者 API 金鑰登入

佇 [app.omi.me](https://app.omi.me) 控制台 **Developer → API Keys** 裡面建立 API 金鑰：
```bash
# 將金鑰保存在目前活動的 profile 裡面
omi auth login --api-key omi_dev_zure_gakoa_hemen

# 或者設定做環境變數（Docker 佮 CI/CD 流程推薦）：
export OMI_API_KEY="omi_dev_zure_gakoa_hemen"
```

> **安全佮優先順序提醒：**
> * 直接佇命令列用 `--api-key`，金鑰會出現佇終端歷史（`shell history`）佮系統行程列表裡面。公用的機器頂懸，用互動模式（`omi auth login`）或者 `OMI_API_KEY` 環境變數。
> * 若是活動的 profile 已經佇設定裡面存了金鑰，伊的優先順序比環境變數較懸。欲用 `OMI_API_KEY`，先用 `omi auth logout` 登出，或者用新的 profile。

### 檢查連線狀態

* `omi auth status`：顯示活動的 profile 佮本地保存的遮罩識別碼（離線會使用得）。
* `omi auth whoami`：向 Omi 伺服器送網路請求，確認連線敢有效。
```bash
omi auth status
omi auth whoami
```

### 登出 (Logout)

欲刪除本地保存的憑證：
```bash
omi auth logout
# 若是有用 OMI_API_KEY 環境變數，將伊取消：
unset OMI_API_KEY
```

> **檔案安全提醒：** 設定保存在 `~/.omi/config.toml` 檔案裡面。佇 Unix/Linux 系統頂懸，建議限制權限：`chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`。

---

## 3. 基本命令

### 記持 (Memories)

保存佮搜揣長期的上下文筆記、事件佮備註：
```bash
# 已經保存的記持列表
omi memory list

# 建立新的記持
omi memory create "使用者較愛有 Python 範例的技術回答" --category work

# 用識別碼提指定的記持
omi memory get <OROITZAPEN_ID>
```

### 對話 (Conversations)

來自 Omi 裝置的錄音佮文字轉錄：
```bash
# 最近 5 个對話的列表
omi conversation list --limit 5

# 提一个對話連伊的完整轉錄
omi conversation get <ELKARRIZKETA_ID> --include-transcript
```

### 待辦佮任務 (Action Items)

佇對話裡面自動偵測著的任務佮行動項：
```bash
# 拍開的任務列表
omi action-item list --open

# 將一个任務標做完成
omi action-item complete <ZEREGIN_ID>
```

### 目標 (Goals)

追蹤長期目標佮進展：
```bash
# 活動的目標列表
omi goal list

# 建立新的定量目標（標題做位置參數傳入）
omi goal create "逐日飲水量" --type numeric --target 2500 --unit "ml"
```

---

## 4. 結構化自動化佮 JSON 輸出 (`--json`)

`omi-cli` 專門為整合佇跤本佮自動化的 AI 流程裡面設計。全域的 `--json` 旗標提供乾淨的 JSON 輸出，用 `jq` 這款工具處理上適合：
```bash
# 用 JSON 格式提記持，用 jq 過濾
omi --json memory list | jq '.[] | {id, content, category}'

# 提出最近 5 个對話的標題
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 拍開的任務列表
omi --json action-item list --open | jq '.'
```

> **主要的語法規則：**
> `--json` 選項是全域的，一定著囥佇子命令的**頭前**：
> * 著的：`omi --json memory list`
> * 毋著的：`omi memory list --json`

### 分頁佮資料匯出

資料量較大的時陣，用 `--limit` 佮 `--offset` 參數：
```bash
# 分頁下載資料
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
omi --json memory list --limit 25 --offset 25 > memories-page-2.json
```

重新導向到檔案會建立或者崁過本地檔案。處理資料進前，一定著檢查命令的結束碼。錯誤訊息會送到標準錯誤（`stderr`），所以空檔案毋代表就無資料。匯出的檔案可能包含機密資料——照你的安全規則保護𪜶。

---

## 5. 結束碼 (Exit Codes Contract)

`omi-cli` 用穩定的結束碼約定，專門為自動化佮 AI 代理設計。零（0）表示成功；任何非零的數字表示有特定意思的錯誤。

| 代碼 | 名 | 意思佮說明 |
| :---: | :--- | :--- |
| `0` | **成功 (`EXIT_OK`)** | 命令正常執行，無錯誤。 |
| `1` | **用法錯誤 / 應用驗證 (`EXIT_USAGE`)** | 應用層的驗證錯誤（`UsageError`，比如講 `--browser` 佮 `--api-key` 兩个袂當鬥陣用的選項做伙指定）。 |
| `2` | **認證錯誤 / 解析錯誤 (`EXIT_AUTH`)** | 憑證無去、金鑰過期或者權限無夠。Click/Typer 的語法錯誤佮無效的選項值嘛轉去代碼 2。 |
| `3` | **伺服器或者網路錯誤 (`EXIT_SERVER`)** | Omi 伺服器的 HTTP 5xx 回應或者網路連線中斷。 |
| `4` | **超過請求限制 (`EXIT_RATE_LIMITED`)** | HTTP 429 回應——短時間裡面送傷濟的請求。 |
| `5` | **資源揣無 (`EXIT_NOT_FOUND`)** | HTTP 404 回應——請求的資源無存在。

---

## 6. 無仝終端環境的範例

自動化跤本裡面，上好永遠佇處理任何資料進前檢查結束碼。詳細的語法愛看你用的是啥物終端：

### Bash / Zsh (Linux 佮 macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "成功提著 $(jq 'length' /tmp/memories.json) 條記持。"
else
    code=$?
    echo "提記持出錯（結束碼：$code）" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)
```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "命令失敗，結束碼 $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "資料保存成功。"
```

### Windows 命令提示字元 (`cmd.exe`)
```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo 出錯去，結束碼 %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo 操作成功完成。
```

---

## 7. Profile 管理佮測試環境 (Staging)

`--profile` 選項會使分開維護幾若个獨立的設定（比如講個人、公司或者測試）。測試環境（staging）來講，會使佇 profile 裡面永久設定 base URL：

> **關於 `--api-base` 選項的重要提醒：** `--api-base` 旗標干焦會使做這條命令的臨時崁過，袂自動保存在設定裡面。欲永久使用，用 `config set api_base <url>`。
```bash
# 予 staging profile 永久設定 base URL
omi --profile staging config set api_base https://api.staging.omi.me

# 佇 staging 測試 profile 頂懸登入
omi --profile staging auth login --api-key omi_dev_staging_gakoa

# 佇 staging profile 裡面走命令（永久指向 staging 環境）
omi --profile staging memory list

# 或者干焦對單條命令做臨時崁過：
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 8. 佮本地桌面 API 整合 (Local Desktop API)

若是 Omi Desktop 應用佇仝一台電腦頂懸咧走，會使直接佮本地伺服器通訊，毋免將資料送去雲。走 `omi local status` 或者搜揣進前，確認位址佮安全令牌已經設定好：
```bash
# 1. 設定本地位址（預設埠 47778）佮令牌：
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="your_local_token"

# 或者佇 profile 裡面永久保存：
# omi local configure --url http://127.0.0.1:47778 --token "your_local_token"

# 2. 檢查本地伺服器的狀態（愛先設定好參數）
omi local status

# 3. 照查詢佮應用搜揣螢幕歷史
omi local search-screen "asteroko bilera" --days 1 --app "Slack"
```

---

## 9. 安全佮最佳實踐

1. **`--json` 旗標的位置：** 永遠囥佇子命令的頭前（`omi --json memory list`）。
2. **處理結束碼：** 佇自動化跤本裡面，永遠檢查佮處理 1 到 5 的代碼。
3. **保護憑證：** 千萬毋通將 API 金鑰上傳去公開的代碼倉庫。生產佮 CI/CD 環境裡面永遠用 `OMI_API_KEY` 變數。
