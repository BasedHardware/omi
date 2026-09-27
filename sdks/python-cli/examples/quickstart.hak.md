# 快速指南：omi-cli (客家話)

`omi-cli` 係 Omi 生態系統个官方命令行界面（CLI）：做得存取 memories（記憶）、conversations（對話）、action items（待辦）同 goals（目標）。這篇指南全部用客家話寫，專門分自動化環境、終端用戶同開發者看。

---

## 1. 安裝 (Installation)

這個包在 PyPI 倉庫用 `omi-cli` 个名發布。安裝好之後，`omi` 命令就會在若个 `$PATH` 裡肚出現：
```bash
# 推薦个方法：用 pipx 个隔離環境
pipx install omi-cli

# 或者用普通个 pip：
pip install omi-cli
```

用檢查版本同幫助信息來確認安裝成功：
```bash
omi --version
omi --help
```

> **注意：** PyPI 包个名係 `omi-cli`（因為另外一個包已經用忒光个 `omi` 个名），毋過終端命令永遠係 `omi`。

---

## 2. 認證 (Authentication)

`omi-cli` 既支持瀏覽器个交互式登錄，也支持開發者 API 密鑰：
```bash
omi auth login
# 1) 瀏覽器——用瀏覽器登錄（Google 或者 Apple）
# 2) API 密鑰——在 app.omi.me 面板粘貼開發者密鑰
```

### 用瀏覽器登錄
```bash
# 用 Google 賬號登錄（默認）
omi auth login --browser

# 用 Apple 賬號登錄
omi auth login --browser --provider apple
```

### 用開發者 API 密鑰登錄

在 [app.omi.me](https://app.omi.me) 控制台 **Developer → API Keys** 裡肚創建 API 密鑰：
```bash
# 將密鑰保存在當前活動个 profile 裡肚
omi auth login --api-key omi_dev_zure_gakoa_hemen

# 或者設置做環境變量（Docker 同 CI/CD 流程推薦）：
export OMI_API_KEY="omi_dev_zure_gakoa_hemen"
```

> **安全同優先級提醒：**
> * 直接在命令行用 `--api-key`，密鑰會出現在終端歷史（`shell history`）同系統進程列表裡肚。共用个機器頂高，用交互模式（`omi auth login`）或者 `OMI_API_KEY` 環境變量。
> * 若係活動个 profile 已經在配置裡肚存忒密鑰，佢个優先級比環境變量還較高。愛用 `OMI_API_KEY`，先用 `omi auth logout` 退出登錄，或者用新个 profile。

### 檢查會話狀態

* `omi auth status`：顯示活動个 profile 同本地保存个掩碼標識（離線做得用）。
* `omi auth whoami`：向 Omi 服務器發送網絡請求，確認會話係毋係有效。
```bash
omi auth status
omi auth whoami
```

### 退出登錄 (Logout)

愛刪除本地保存个憑證：
```bash
omi auth logout
# 若係有用 OMI_API_KEY 環境變量，將佢取消：
unset OMI_API_KEY
```

> **文件安全提醒：** 配置保存在 `~/.omi/config.toml` 文件裡肚。在 Unix/Linux 系統頂高，建議限制權限：`chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`。

---

## 3. 基本命令

### 記憶 (Memories)

保存同搜索長期个上下文筆記、事件同備註：
```bash
# 已保存个記憶列表
omi memory list

# 創建新个記憶
omi memory create "用戶較喜歡帶 Python 示例个技術回答" --category work

# 用標識符獲取指定个記憶
omi memory get <OROITZAPEN_ID>
```

### 對話 (Conversations)

來自 Omi 設備个音頻錄音同文字轉錄：
```bash
# 最近 5 隻對話个列表
omi conversation list --limit 5

# 獲取一隻對話連佢个完整轉錄
omi conversation get <ELKARRIZKETA_ID> --include-transcript
```

### 待辦同任務 (Action Items)

在對話裡肚自動檢測着个任務同行動項：
```bash
# 打開个任務列表
omi action-item list --open

# 將一隻任務標記做完成
omi action-item complete <ZEREGIN_ID>
```

### 目標 (Goals)

跟蹤長期目標同進展：
```bash
# 活動个目標列表
omi goal list

# 創建新个定量目標（標題做位置參數傳入）
omi goal create "每日飲水量" --type numeric --target 2500 --unit "ml"
```

---

## 4. 結構化自動化同 JSON 輸出 (`--json`)

`omi-cli` 專門為集成在腳本同自動化个 AI 流程裡肚設計。全局个 `--json` 標誌提供乾淨个 JSON 輸出，用 `jq` 這種工具處理最合適：
```bash
# 用 JSON 格式獲取記憶，用 jq 過濾
omi --json memory list | jq '.[] | {id, content, category}'

# 提取最近 5 隻對話个標題
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 打開个任務列表
omi --json action-item list --open | jq '.'
```

> **主要个語法規則：**
> `--json` 選項係全局个，一定要放在子命令个**前肚**：
> * 着个：`omi --json memory list`
> * 毋着个：`omi memory list --json`

### 分頁同數據導出

數據量較大个時節，用 `--limit` 同 `--offset` 參數：
```bash
# 分頁下載數據
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
omi --json memory list --limit 25 --offset 25 > memories-page-2.json
```

重定向到文件會創建或者覆蓋本地文件。處理數據之前，一定愛檢查命令个退出碼。錯誤信息會送到標準錯誤（`stderr`），所以空文件毋代表就無數據。導出个文件可能包含機密數據——按若个安全規則保護佢等。

---

## 5. 退出碼 (Exit Codes Contract)

`omi-cli` 用穩定个退出碼約定，專門為自動化同 AI 代理設計。零（0）表示成功；任何非零个數字表示有特定意思个錯誤。

| 代碼 | 名 | 意思同描述 |
| :---: | :--- | :--- |
| `0` | **成功 (`EXIT_OK`)** | 命令正常執行，無錯誤。 |
| `1` | **用法錯誤 / 應用驗證 (`EXIT_USAGE`)** | 應用層个驗證錯誤（`UsageError`，比如講 `--browser` 同 `--api-key` 兩個毋兼容个選項共下指定）。 |
| `2` | **認證錯誤 / 解析錯誤 (`EXIT_AUTH`)** | 憑證無忒、密鑰過期或者權限毋罅。Click/Typer 个語法錯誤同無效个選項值乜返回代碼 2。 |
| `3` | **服務器或者網絡錯誤 (`EXIT_SERVER`)** | Omi 服務器个 HTTP 5xx 響應或者網絡連接中斷。 |
| `4` | **超過請求限制 (`EXIT_RATE_LIMITED`)** | HTTP 429 響應——短時間裡肚發送忒多个請求。 |
| `5` | **資源無尋着 (`EXIT_NOT_FOUND`)** | HTTP 404 響應——請求个資源毋存在。

---

## 6. 毋同終端環境个示例

自動化腳本裡肚，最好永遠在處理任何數據之前檢查退出碼。具體个語法愛看若用个係麼个終端：

### Bash / Zsh (Linux 同 macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "成功獲取忒 $(jq 'length' /tmp/memories.json) 條記憶。"
else
    code=$?
    echo "獲取記憶出錯（退出碼：$code）" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)
```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "命令失敗，退出碼 $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "數據保存成功。"
```

### Windows 命令提示符 (`cmd.exe`)
```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo 出錯忒，退出碼 %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo 操作成功完成。
```

---

## 7. Profile 管理同測試環境 (Staging)

`--profile` 選項做得分開維護多隻獨立个配置（比如講個人、公司或者測試）。測試環境（staging）來講，做得在 profile 裡肚永久設置 base URL：

> **關於 `--api-base` 選項个重要提醒：** `--api-base` 標誌淨做得做這條命令个臨時覆蓋，毋會自動保存在配置裡肚。愛永久使用，用 `config set api_base <url>`。
```bash
# 為 staging profile 永久設置 base URL
omi --profile staging config set api_base https://api.staging.omi.me

# 在 staging 測試 profile 頂高登錄
omi --profile staging auth login --api-key omi_dev_staging_gakoa

# 在 staging profile 裡肚運行命令（永久指向 staging 環境）
omi --profile staging memory list

# 或者淨對單條命令做臨時覆蓋：
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 8. 同本地桌面 API 集成 (Local Desktop API)

若係 Omi Desktop 應用在共隻電腦頂高運行，做得直接同本地服務器通信，毋使將數據送到雲。運行 `omi local status` 或者搜索之前，確認地址同安全令牌已經設置好：
```bash
# 1. 設置本地地址（默認端口 47778）同令牌：
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="your_local_token"

# 或者在 profile 裡肚永久保存：
# omi local configure --url http://127.0.0.1:47778 --token "your_local_token"

# 2. 檢查本地服務器个狀態（愛先設置好參數）
omi local status

# 3. 按查詢同應用搜索屏幕歷史
omi local search-screen "asteroko bilera" --days 1 --app "Slack"
```

---

## 9. 安全同最佳實踐

1. **`--json` 標誌个位置：** 永遠放在子命令个前肚（`omi --json memory list`）。
2. **處理退出碼：** 在自動化腳本裡肚，永遠檢查同處理 1 到 5 个代碼。
3. **保護憑證：** 千萬毋好將 API 密鑰上傳到公開个代碼倉庫。生產同 CI/CD 環境裡肚永遠用 `OMI_API_KEY` 變量。
