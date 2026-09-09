# omi-cli 正體中文（繁體中文）快速入門指南

> 透過終端機與 Omi 互動的實用指南，專為人類使用者與 AI Agent 設計。

> [!NOTE]
> 本文件為正體中文（繁體中文）快速入門指南。英文版 [README.md](../README.md) 為功能與參數變更的最終權威來源（Single Source of Truth）。

`omi-cli` 是操作 [Omi](https://omi.me) 開發者 API 的官方命令列介面工具。
它提供小巧、可指令碼化且以 JSON 優先的指令，讓您高效管理 Omi 為您維護的四項核心資源：記憶（Memories）、對話（Conversations）、待辦事項（Action Items）以及目標（Goals）。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **官方文件:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **原始碼:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安裝指南 (Installation)

建議使用 `pipx` 進行安裝，這樣可以將相依套件隔離在獨立的虛擬環境中：

```bash
# 推薦做法：使用 pipx 安裝（環境隔離）
pipx install omi-cli

# 或使用標準 pip 安裝
pip install omi-cli
```

> **重要說明：套件名稱與指令名稱的差異**
> * 在 PyPI 上的套件名稱是 **`omi-cli`**（請勿安裝名稱相近但毫無關聯的 `omi` 套件）。
> * 安裝完成後，在終端機中執行的可執行檔名稱則是 **`omi`**。

安裝後請確認版本與說明資訊：

```bash
omi --version
omi --help
```

---

## 2. 身份驗證 (Authentication)

`omi-cli` 支援兩種主要的驗證方式：

| 驗證方式 | 主要適用場景 | 指令範例 |
| :--- | :--- | :--- |
| **開發者 API 金鑰 (`omi_dev_*`)** | CI/CD、自動化指令碼、AI Agent | `omi auth login --api-key ...` 或環境變數 |
| **瀏覽器 OAuth (Google/Apple)** | 開發者的本機電腦與筆記型電腦 | `omi auth login --browser` |

### 互動式登入
直接執行不帶參數的指令，會出現選擇登入方式的互動選單：

```bash
omi auth login
# 1) Browser — 使用 Google 或 Apple 帳號登入（推薦人類開發者使用）
# 2) API key — 貼上在 app.omi.me 產生的開發者金鑰（推薦 Agent 與 CI 使用）
```

### 直接透過瀏覽器登入
```bash
omi auth login --browser
```

### 使用開發者 API 金鑰
請至 [app.omi.me](https://app.omi.me) 的「Developer → API Keys」頁面建立並複製開發者金鑰：

```bash
# 透過指令設定
omi auth login --api-key omi_dev_...

# 或透過環境變數設定（最適合 CI/CD 與容器環境）
export OMI_API_KEY="omi_dev_..."
```

### 驗證登入狀態
* `omi auth status`：僅讀取本機儲存的認證設定檔與過期時間（**離線執行**，不發送網路請求）。
* `omi auth whoami`：向 Omi 伺服器發送實際的驗證請求，確認金鑰或憑證仍有效且未過期（**需要網路連線**）。

```bash
omi auth status
omi auth whoami
```

登出目前的帳號：
```bash
omi auth logout
```

---

## 3. 核心資源操作 (Core Resources)

您可以透過 `omi` 指令操作四大核心資源。

### 記憶 (Memories)
系統所學習到關於您的事實、偏好與背景知識。

```bash
# 列出記憶清單
omi memory list

# 建立新記憶
omi memory create "使用者偏好深色模式" --category lifestyle

# 查詢特定記憶詳情
omi memory get <MEMORY_ID>
```

### 對話 (Conversations)
由硬體穿戴裝置或應用程式所擷取並處理的語音與文字對話紀錄。

```bash
# 列出最近 5 筆對話
omi conversation list --limit 5

# 檢視特定對話詳情並包含逐字稿 (Transcript)
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 待辦事項 (Action Items)
從對話內容中自動擷取出的任務與後續追蹤事項。

```bash
# 僅列出未完成 (Open) 的待辦事項
omi action-item list --open

# 將待辦事項標記為已完成
omi action-item complete <ACTION_ITEM_ID>
```

### 目標 (Goals)
追蹤個人長期進度的量化與定性目標。

```bash
# 列出所有追蹤中的目標
omi goal list
```

---

## 4. 自動化指令碼與 JSON 輸出 (`--json`)

`omi-cli` 原生支援結構化 JSON 輸出。當與 `jq`、Shell 指令碼或 AI Agent 流程搭配時，請將 `--json` 作為**全域旗標（Global Flag）**放在子指令**之前**：

```bash
# 以 JSON 格式取得記憶清單，並使用 jq 篩選 id、content 與 category
omi --json memory list | jq '.[] | {id, content, category}'

# 取得最近對話的標題與開始時間
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 列出未完成待辦事項的完整 JSON 結構
omi --json action-item list --open | jq '.'
```

> **重點提示：`--json` 的位置規則**
> * 正確用法（放在子指令之前）：`omi --json memory list`
> * 錯誤用法（放在子指令之後）：`omi memory list --json`

---

## 5. 結束代碼規範 (Exit Codes)

在編寫自動化指令碼或 CI 檢查時，`omi-cli` 遵循明確且穩定的結束代碼規格：

| 結束代碼 | 代表意義 | 說明與處置建議 |
| :---: | :--- | :--- |
| `0` | 成功 (Success) | 指令正常執行完畢 |
| `1` | 指令用法錯誤 (Usage Error) | 傳入無效參數或缺少必要引數 |
| `2` | 身份驗證錯誤 (Auth Error) | 未登入、API 金鑰無效或 Token 已過期 |
| `3` | 伺服器錯誤 (Server Error) | 收到 5xx 錯誤回應、連線超時或網路故障 |
| `4` | 請求頻率受限 (Rate Limited) | 429 Too Many Requests，請實作指數退避重試 |
| `5` | 資源不存在 (Not Found) | 404 Not Found，找不到指定的 ID |

---

## 6. 各作業系統 Shell 環境變數設定範例

### Bash / Zsh (Linux / macOS)
```bash
# 設定 API 金鑰
export OMI_API_KEY="omi_dev_your_actual_key_here"

# 執行查詢
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# 設定 API 金鑰
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# 使用 PowerShell 原生 JSON 解析
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. 本機 Desktop API 與憑證隔離

在已啟動 Omi Desktop 本機應用程式的電腦上，您可以繞過雲端 API，直接存取本機螢幕歷史紀錄與本機 SQL 資料庫。本機憑證與雲端 API 憑證彼此獨立：

```bash
# 設定本機 Desktop API 網址與存取權杖
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# 檢查本機連線狀態
omi --json local status

# 搜尋本機螢幕歷史紀錄
omi --json local search-screen "定價方案" --days 7 --app Safari
```

---

## 8. 多設定檔切換 (Profiles)

若您需要在不同帳號或不同環境（例如個人帳號、工作環境或測試環境）之間切換，可使用全域 `--profile` 旗標。所有設定檔皆安全儲存在 `~/.omi/config.toml`：

```bash
# 使用個人設定檔登入
omi --profile personal auth login

# 使用工作設定檔登入
omi --profile work auth login

# 指定設定檔執行指令
omi --profile work memory list
```
