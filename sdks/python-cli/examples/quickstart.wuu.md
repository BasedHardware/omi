# 快速指南：omi-cli (吳語)

`omi-cli` 是 Omi 生態系統個官方命令行界面（CLI）：可以訪問 memories（記憶）、conversations（對話）、action items（待辦）搭 goals（目標）。箇篇指南全部用吳語寫，專門畀自動化環境、終端用戶搭開發者看。

---

## 1. 安裝 (Installation)

箇隻包勒 PyPI 倉庫用 `omi-cli` 箇隻名字發佈。安裝好之後，`omi` 命令就會勒儂個 `$PATH` 裏向出現：
```bash
# 推薦個方法：用 pipx 個隔離環境
pipx install omi-cli

# 或者用普通個 pip：
pip install omi-cli
```

用檢查版本搭幫助信息來確認安裝成功：
```bash
omi --version
omi --help
```

> **注意：** PyPI 包個名字是 `omi-cli`（因爲另外一隻包已經用脫光個 `omi` 箇隻名字），勿過終端命令永遠是 `omi`。

---

## 2. 認證 (Authentication)

`omi-cli` 既支持瀏覽器個交互式登錄，也支持開發者 API 密鑰：
```bash
omi auth login
# 1) 瀏覽器——用瀏覽器登錄（Google 或者 Apple）
# 2) API 密鑰——勒 app.omi.me 面板粘貼開發者密鑰
```

### 用瀏覽器登錄
```bash
# 用 Google 賬號登錄（默認）
omi auth login --browser

# 用 Apple 賬號登錄
omi auth login --browser --provider apple
```

### 用開發者 API 密鑰登錄

勒 [app.omi.me](https://app.omi.me) 控制枱 **Developer → API Keys** 裏向創建 API 密鑰：
```bash
# 將密鑰保存勒當前活動個 profile 裏向
omi auth login --api-key omi_dev_zure_gakoa_hemen

# 或者設置成環境變量（Docker 搭 CI/CD 流程推薦）：
export OMI_API_KEY="omi_dev_zure_gakoa_hemen"
```

> **安全搭優先級提醒：**
> * 直接勒命令行裏向用 `--api-key`，密鑰會出現勒終端歷史（`shell history`）搭系統進程列表裏向。公用個機器浪向，用交互模式（`omi auth login`）或者 `OMI_API_KEY` 環境變量。
> * 如果活動個 profile 已經勒配置裏向存好密鑰，伊個優先級比環境變量還要高。要用 `OMI_API_KEY`，先用 `omi auth logout` 退出登錄，或者用新個 profile。

### 檢查會話狀態

* `omi auth status`：顯示活動個 profile 搭本地保存個掩碼標識（離線可以用）。
* `omi auth whoami`：向 Omi 服務器發送網絡請求，確認會話是勿是有效。
```bash
omi auth status
omi auth whoami
```

### 退出登錄 (Logout)

要刪除本地保存個憑證：
```bash
omi auth logout
# 如果用過 OMI_API_KEY 環境變量，將伊取消脫：
unset OMI_API_KEY
```

> **文件安全提醒：** 配置保勒 `~/.omi/config.toml` 文件裏向。勒 Unix/Linux 系統浪向，建議限制權限：`chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`。

---

## 3. 基本命令

### 記憶 (Memories)

保存搭搜索長期個上下文筆記、事件搭備註：
```bash
# 已保存個記憶列表
omi memory list

# 創建新個記憶
omi memory create "用戶比較歡喜帶 Python 示例個技術回答" --category work

# 用標識符獲取指定個記憶
omi memory get <OROITZAPEN_ID>
```

### 對話 (Conversations)

來自 Omi 設備個音頻錄音搭文字轉錄：
```bash
# 最近 5 隻對話個列表
omi conversation list --limit 5

# 獲取一隻對話連伊個完整轉錄
omi conversation get <ELKARRIZKETA_ID> --include-transcript
```

### 待辦搭任務 (Action Items)

勒對話裏向自動檢測着個任務搭行動項：
```bash
# 還沒完成個任務列表
omi action-item list --open

# 將一隻任務標記成完成
omi action-item complete <ZEREGIN_ID>
```

### 目標 (Goals)

跟蹤長期目標搭進展：
```bash
# 活動個目標列表
omi goal list

# 創建新個定量目標（標題做位置參數傳入）
omi goal create "逐日飲水量" --type numeric --target 2500 --unit "ml"
```

---

## 4. 結構化自動化搭 JSON 輸出 (`--json`)

`omi-cli` 專門爲集成勒腳本搭自動化個 AI 流程裏向設計。全局個 `--json` 標誌提供乾淨個 JSON 輸出，用 `jq` 迭種工具處理頂合適：
```bash
# 用 JSON 格式獲取記憶，用 jq 過濾
omi --json memory list | jq '.[] | {id, content, category}'

# 提取最近 5 隻對話個標題
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 還沒完成個任務列表
omi --json action-item list --open | jq '.'
```

> **主要個語法規則：**
> `--json` 選項是全局個，一定要放勒子命令個**前頭**：
> * 對個：`omi --json memory list`
> * 勿對個：`omi memory list --json`

### 分頁搭數據導出

數據量比較大個辰光，用 `--limit` 搭 `--offset` 參數：
```bash
# 分頁下載數據
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
omi --json memory list --limit 25 --offset 25 > memories-page-2.json
```

重定向到文件會創建或者覆蓋本地文件。處理數據之前，一定記得檢查命令個退出碼。錯誤信息會送到標準錯誤（`stderr`），所以空文件勿代表就嘸沒數據。導出個文件可能包含機密數據——按儂個安全規則保護渠拉。

---

## 5. 退出碼 (Exit Codes Contract)

`omi-cli` 用穩定個退出碼約定，專門爲自動化搭 AI 代理設計。零（0）表示成功；任何非零個數字表示有特定意思個錯誤。

| 代碼 | 名 | 意思搭描述 |
| :---: | :--- | :--- |
| `0` | **成功 (`EXIT_OK`)** | 命令正常執行，嘸沒錯誤。 |
| `1` | **用法錯誤 / 應用驗證 (`EXIT_USAGE`)** | 應用層個驗證錯誤（`UsageError`，比方講 `--browser` 搭 `--api-key` 兩隻勿兼容個選項一道指定）。 |
| `2` | **認證錯誤 / 解析錯誤 (`EXIT_AUTH`)** | 憑證嘸沒、密鑰過期或者權限勿夠。Click/Typer 個語法錯誤搭無效個選項值也返回代碼 2。 |
| `3` | **服務器或者網絡錯誤 (`EXIT_SERVER`)** | Omi 服務器個 HTTP 5xx 響應或者網絡連接中斷。 |
| `4` | **超過請求限制 (`EXIT_RATE_LIMITED`)** | HTTP 429 響應——短辰光裏向發送忒多个請求。 |
| `5` | **資源尋勿着 (`EXIT_NOT_FOUND`)** | HTTP 404 響應——請求個資源勿存在。

---

## 6. 勿同終端環境個例子

自動化腳本裏向，頂好永遠勒處理任何數據之前檢查退出碼。具體個語法要看儂用個是啥終端：

### Bash / Zsh (Linux 搭 macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "成功獲取着 $(jq 'length' /tmp/memories.json) 條記憶。"
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
    echo 出錯哉，退出碼 %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo 操作成功完成。
```

---

## 7. Profile 管理搭測試環境 (Staging)

`--profile` 選項可以分開維護幾隻獨立個配置（比方講個人、公司或者測試）。測試環境（staging）來講，可以勒 profile 裏向永久設置 base URL：

> **關於 `--api-base` 選項個重要提醒：** `--api-base` 標誌衹好做迭條命令個臨時覆蓋，勿會自動保存勒配置裏向。要永久使用，用 `config set api_base <url>`。
```bash
# 畀 staging profile 永久設置 base URL
omi --profile staging config set api_base https://api.staging.omi.me

# 勒 staging 測試 profile 浪向登錄
omi --profile staging auth login --api-key omi_dev_staging_gakoa

# 勒 staging profile 裏向運行命令（永久指向 staging 環境）
omi --profile staging memory list

# 或者衹對單條命令做臨時覆蓋：
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 8. 同本地桌面 API 集成 (Local Desktop API)

如果 Omi Desktop 應用勒衕一隻電腦浪向運行，可以直接搭本地服務器通信，勿用將數據送到雲。運行 `omi local status` 或者搜索之前，確認地址搭安全令牌已經設置好：
```bash
# 1. 設置本地地址（默認端口 47778）搭令牌：
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="your_local_token"

# 或者勒 profile 裏向永久保存：
# omi local configure --url http://127.0.0.1:47778 --token "your_local_token"

# 2. 檢查本地服務器個狀態（要先設置好參數）
omi local status

# 3. 按查詢搭應用搜索屏幕歷史
omi local search-screen "asteroko bilera" --days 1 --app "Slack"
```

---

## 9. 安全搭最佳實踐

1. **`--json` 標誌個位置：** 永遠放勒子命令個前頭（`omi --json memory list`）。
2. **處理退出碼：** 勒自動化腳本裏向，永遠檢查搭處理 1 到 5 個代碼。
3. **保護憑證：** 千萬勿要將 API 密鑰上傳到公開個代碼倉庫。生產搭 CI/CD 環境裏向永遠用 `OMI_API_KEY` 變量。
