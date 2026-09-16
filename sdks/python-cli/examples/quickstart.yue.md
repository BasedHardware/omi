# omi-cli — 粵語快速上手指南

> 喺終端機用 Omi 嘅實戰指南。人類同 AI 代理都啱用。

`omi-cli` 係 [Omi](https://omi.me) 開發者 API 嘅官方指令行客戶端。
佢提供快速又方便寫腳本嘅方式,存取 Omi 四個核心實體:
記憶、對話、待辦事項同埋目標。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **文件:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **原始碼:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安裝

建議用 `pipx`:佢會將工具裝喺獨立環境入面,
咁樣佢嘅依賴套件就唔會同你嘅專案衝突。

```bash
# 建議:用 pipx 安裝
pipx install omi-cli

# 或者用 pip
pip install omi-cli
```

> **重要:套件名同指令名係唔同嘅。**
> * 安裝嘅套件係 **`omi-cli`**(另外嗰個 `omi` 套件係另一個完全冇關係嘅專案)。
> * 裝完之後,你執行嘅指令係 **`omi`**。

檢查吓係咪裝好:

```bash
omi --version
omi --help
```

---

## 2. 登入驗證

`omi-cli` 支援兩種登入方法。

| 方法 | 啱用於 | 指令 |
| :--- | :--- | :--- |
| **開發者金鑰(`omi_dev_*`)** | CI/CD、腳本、AI 代理 | `omi auth login --api-key ...` 或者環境變數 |
| **瀏覽器登入(Google/Apple)** | 喺自己電腦度做嘢 | `omi auth login --browser` |

### 互動式登入

冇旗標嘅話,指令會自己問你想用邊種方法:

```bash
omi auth login
# 1) Browser — 用 Google 或者 Apple 登入(人類用起嚟方便)
# 2) API key — 貼上由 app.omi.me 攞嘅開發者金鑰(代理同 CI 用起嚟方便)
```

如果揀金鑰,輸入會被遮住,咁金鑰就唔會留喺終端機記錄度。

### 直接用瀏覽器

```bash
omi auth login --browser
```

### 用開發者金鑰

金鑰喺 [app.omi.me](https://app.omi.me) 嘅 **Developer → API Keys** 攞。

```bash
# 將金鑰存落設定度
omi auth login --api-key omi_dev_...

# 或者透過環境傳入 — CI/CD 同容器首選
export OMI_API_KEY=omi_dev_...
```

`OMI_API_KEY` 環境變數喺現用設定檔冇存金鑰嗰陣先會用到,
所以喺容器入面就唔使寫嘢落碟。如果個設定檔已經有金鑰,
佢會優先過環境變數。

### 檢查登入狀態

兩個指令答緊唔同嘅問題,唔好搞亂:

* `omi auth status` — **本機**存咗啲乜:設定檔、遮住咗嘅金鑰、到期日。
  冇網絡都用得。
* `omi auth whoami` — **問 Omi 伺服器**:檢查金鑰係咪真係
  會被接受。需要網絡。

```bash
omi auth status    # 本機檢查,離線都得
omi auth whoami    # 喺伺服器度檢查
```

更新一個就嚟到期嘅 OAuth 工作階段,唔使重新登入 — 只適用於瀏覽器登入(OAuth)。對 `omi_dev_*` 金鑰嚟講,呢個指令唔會做任何更新;請喺網頁應用程式嘅 `Developer → API Keys` 度換條新金鑰:

```bash
omi auth refresh
```

登出:

```bash
omi auth logout
```

---

## 3. 基本指令

### 記憶(memories)

系統記住嘅關於你嘅事實同知識。

```bash
# 記憶清單
omi memory list

# 整一條新嘅
omi memory create "用戶鍾意深色主題" --category lifestyle

# 睇某一條
omi memory get <MEMORY_ID>
```

### 對話(conversations)

嚟自裝置或者應用程式嘅語音同文字記錄。

```bash
# 最近 5 個對話
omi conversation list --limit 5

# 完整對話連謄本
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 待辦事項(action items)

Omi 由對話度推斷出嚟嘅工作。

```bash
# 淨係未完成嘅
omi action-item list --open

# 標記做咗
omi action-item complete <ACTION_ITEM_ID>
```

### 目標(goals)

```bash
# 目標清單
omi goal list

# 記低一個新嘅進度數值(兩個引數都要:目標同數值)
omi goal progress <GOAL_ID> 25

# 修改記錄
omi goal history <GOAL_ID>
```

---

## 用自己嘅字眼問嘢(`ask`)

一個獨立嘅頂層指令:用自然語言發問,
答案會由你自己嘅對話砌出嚟。

```bash
omi ask "搬屋嗰單嘢我決定咗啲乜"
omi --json ask "我應承咗今個禮拜搞掂邊啲嘢"
```

---

## 4. JSON 同腳本(`--json`)

`omi-cli` 可以輸出機器讀得嘅 JSON。`--json` 呢個旗標係**全域**嘅,
所以要放喺子指令**之前**。

```bash
# 記憶:抽出 id、內容同分類
omi --json memory list | jq '.[] | {id, content, category}'

# 最近對話嘅標題
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 未完成嘅待辦事項
omi --json action-item list --open | jq '.'
```

> **常見錯誤。** `--json` 要放喺子指令前面,唔係後面。
> * 啱:`omi --json memory list`
> * 錯:`omi memory list --json`

喺 `--json` 模式之下,stdout 淨係會輸出 JSON 本身 —
腳本可以信得過。

---

## 5. 結束代碼(exit codes)

代碼係穩定嘅,所以腳本同 CI 嘅邏輯可以按佢哋分岔。

| 代碼 | 意思 | 幾時出現 |
| :---: | :--- | :--- |
| `0` | 成功 | 指令執行完成 |
| `1` | 呼叫錯誤 | omi-cli 自己嘅驗證(例如同時用 `--browser` 同 `--api-key`、登入選項唔啱、stdin 係空) |
| `2` | 存取或者引數錯誤 | 未登入、金鑰無效或者過咗期 — 亦包括解析器錯誤(唔識嘅旗標、欠引數) |
| `3` | 伺服器錯誤 | 5xx 回應、逾時、冇連線 |
| `4` | 請求太多 | 429 Too Many Requests |
| `5` | 搵唔到 | 404,個 id 唔存在 |

Bash 入面檢查嘅例子:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "金鑰用得"
else
  code=$?
  [ "$code" -eq 2 ] && echo "請重新登入"
  [ "$code" -eq 3 ] && echo "伺服器冇回應,遲啲再試"
fi
```

---

## 6. 環境變數

### Bash / Zsh(Linux、macOS)

```bash
export OMI_API_KEY="omi_dev_你嘅金鑰"

omi --json memory list --limit 10
```

想金鑰喺新嘅工作階段都載入到,就將嗰行加落 `~/.bashrc` 或者 `~/.zshrc`。

### PowerShell(Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_你嘅金鑰"

# 用 PowerShell 解析 JSON
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

永久設定:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_你嘅金鑰", "User")
```

---

## 7. 本機嘅 Omi Desktop 應用程式

如果 Omi 桌面應用程式行緊,部分資料可以直接攞,
唔使繞過雲端。

```bash
# 指定本機 API 嘅地址
omi local configure --url http://127.0.0.1:47778 --token 你嘅權杖

# 檢查佢有冇回應
omi --json local status

# 喺螢幕記錄度搜尋
omi --json local search-screen "價錢" --days 7 --app Safari

# 按 id 攞截圖
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# 對本機資料庫落任意 SQL
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

工作流程:先 `local status`,跟住 `local tools` — 睇吓有咩工具
同埋佢哋嘅參數,之後先至呼叫。

---

## 8. 設定檔(profiles)

如果你有幾個帳戶或者環境,用設定檔將佢哋分開。
設定會存喺 `~/.omi/config.toml`。

```bash
# 登入私人設定檔
omi --profile personal auth login

# 登入工作設定檔
omi --profile work auth login

# 喺指定設定檔執行指令
omi --profile work memory list
```

如果你冇指定設定檔,CLI 會先用 `OMI_PROFILE` 環境變數嘅值,再用設定檔案嘅現用設定檔,最後用 `default`。優先次序:`--profile` → `OMI_PROFILE` → `~/.omi/config.toml` 嘅現用設定檔 → `default`。

睇同改設定本身:

```bash
# 而家設定咗啲乜
omi config show

# 設定檔案喺邊
omi config path

# 改一個值
omi config set api_base https://api.omi.me
```

---

## 9. 下一步

* [`agent_quickstart.md`](./agent_quickstart.md) — 點樣將 `omi-cli` 駁落 AI 代理度。
* [`shell_examples.sh`](./shell_examples.sh) — 現成嘅 shell 例子。
* [Omi 文件](https://docs.omi.me/doc/developer/cli/introduction) — 完整指令參考。
