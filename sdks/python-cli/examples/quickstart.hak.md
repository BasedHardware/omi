# omi-cli — 客語快速上手指南

> 在終端機操作 Omi 个實用指南。人搭 AI 代理人都用得。

`omi-cli` 係 [Omi](https://omi.me) 開發者 API 个官方命令行客戶端。
佢對 Omi 个四個主要資源 — 記憶、對話、行動項目、目標 — 提供快速、可寫腳本个存取。

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **文件:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **原始碼:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安裝

建議用 `pipx`:佢會摎工具裝到獨立个環境,
毋會摎你專案个相依套件相衝突。

```bash
# 建議:用 pipx 安裝
pipx install omi-cli

# 抑係用 pip
pip install omi-cli
```

> **重要:套件名摎命令名無共樣。**
> * 裝个套件係 **`omi-cli`** (`omi` 係另外一個無相關个專案)。
> * 安裝好後執行个命令係 **`omi`**。

確認一下係毋係做得用:

```bash
omi --version
omi --help
```

---

## 2. 驗證

`omi-cli` 支援兩種登入方式。

| 方式 | 適合 | 命令 |
| :--- | :--- | :--- |
| **開發者金鑰 (`omi_dev_*`)** | CI/CD、腳本、AI 代理人 | `omi auth login --api-key ...` 或者環境變數 |
| **瀏覽器登入 (Google/Apple)** | 在自家電腦做工 | `omi auth login --browser` |

### 互動式登入

毋帶選項執行,佢會問你想用麼个方式。

```bash
omi auth login
# 1) Browser — 用 Google 抑係 Apple 登入(分人用)
# 2) API key — 摎 app.omi.me 提來个開發者金鑰貼上去(分代理人/CI)
```

選金鑰个話,輸入會藏起來,金鑰毋會留到終端機歷史裡肚。

### 直接用瀏覽器登入

```bash
omi auth login --browser
```

### 用開發者金鑰登入

金鑰在 [app.omi.me](https://app.omi.me) 个 **Developer → API Keys** 提。

```bash
# 摎金鑰存到設定
omi auth login --api-key omi_dev_...

# 抑係用環境變數傳 — 分 CI/CD 摎容器較好
export OMI_API_KEY=omi_dev_...
```

`OMI_API_KEY` 環境變數在作用中个設定檔無存金鑰時正會用,
所以在容器裡肚毋使寫東西到硬碟。若係設定檔已經有金鑰,
該支金鑰个優先序比環境變數較高。

### 檢查存取

兩隻命令答个係無共樣个問題,毋好紊雜:

* `omi auth status` — **本地**存个麼个:設定檔、藏起來个金鑰、到期日。
  毋使網路。
* `omi auth whoami` — 對 **Omi 伺服器** 个請求:確認金鑰係真个會接受。
  需要網路。

```bash
omi auth status    # 本地檢查,離線做得
omi auth whoami    # 伺服器檢查
```

摎將到期个權杖毋使再登入就更新 — 這隻命令淨適用 **瀏覽器/OAuth 工作階段**。
用 API 金鑰(`omi_dev_*`)驗證个設定檔,`omi auth refresh` 會因為用法錯誤(代碼 1)
失敗 — 無權杖好更新 — 有需要就到 Omi 網頁應用換金鑰:

```bash
omi auth refresh
```

登出:

```bash
omi auth logout
```

---

## 3. 基本命令

### 記憶 (memories)

系統記著你个事實摎知識。

```bash
# 記憶清單
omi memory list

# 新增一個
omi memory create "使用者較意暗色主題" --category lifestyle

# 看特定一个
omi memory get <MEMORY_ID>
```

### 對話 (conversations)

裝置抑係應用个語音摎文字歷史。

```bash
# 最新个 5 隻對話
omi conversation list --limit 5

# 帶逐字稿个完整對話
omi conversation get <CONVERSATION_ID> --include-transcript
```

### 行動項目 (action items)

Omi 對對話推論出來个任務。

```bash
# 淨看無完成个
omi action-item list --open

# 標示做完成
omi action-item complete <ACTION_ITEM_ID>
```

### 目標 (goals)

```bash
# 目標清單
omi goal list

# 記錄新个進度值(需要兩個參數:目標摎數值)
omi goal progress <GOAL_ID> 25

# 改變歷史
omi goal history <GOAL_ID>
```

---

## 用自然語言問 (`ask`)

另外一隻頂層命令:接受自然語言个問題,
答案對你个對話建起來。

```bash
omi ask "徙屋个事情我決定麼个"
omi --json ask "這隻禮拜我應承愛完成麼个行動項目"
```

---

## 4. JSON 摎腳本 (`--json`)

`omi-cli` 做得產生機器讀得个 JSON。`--json` 選項係 **全域**,
愛放在子命令个 **頭前**。

```bash
# 記憶:提出 id、文字、類別
omi --json memory list | jq '.[] | {id, content, category}'

# 最近對話个標題
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# 無完成个行動項目
omi --json action-item list --open | jq '.'
```

> **常見个毋著。** `--json` 在子命令頭前,毋係後背。
> * 著: `omi --json memory list`
> * 毋著: `omi memory list --json`

`--json` 模式裡肚,分人看个進度訊息摎轉圈仔無咧 —
stdout 淨有一隻有效个 JSON 文件。錯誤去 stderr,
形狀係 `{"error": "...", "detail": "..."}`。

---

## 5. 結束代碼

腳本用來分岔个穩定結束代碼。

| 代碼 | 意思 |
| :--- | :--- |
| `0` | 成功 |
| `1` | 用法錯誤(旗標毋著、必要个參數無) |
| `2` | 驗證失敗 — 需要登入 |
| `3` | 伺服器/網路錯誤 |
| `4` | 速率限制 — 過一下子再試 |
| `5` | 資源尋無 |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "該個記憶無在" ;;
    *) echo "錯誤 $code" ;;
  esac
fi
```

---

## 6. 設定檔摎設定

若係你有幾隻帳號抑係環境,用設定檔分開。
設定存在 `~/.omi/config.toml`。

```bash
# 登入個人設定檔
omi --profile personal auth login

# 登入工作設定檔
omi --profile work auth login

# 在特定設定檔執行命令
omi --profile work memory list
```

用麼个設定檔按這隻順序決定:`--profile` 選項(抑係 `-p`)
優先全部;正係 `OMI_PROFILE` 環境變數;正係 `~/.omi/config.toml`
个作用中設定檔;尾 `default` 設定檔做後備。

看摎改自家个設定:

```bash
# 這下設个係麼个
omi config show

# 設定檔案在哪
omi config path

# 改數值
omi config set api_base https://api.omi.me
```

---

## 7. 下一步

* [`agent_quickstart.md`](./agent_quickstart.md) — 摎 `omi-cli` 接 AI 代理人个方式。
* [`shell_examples.sh`](./shell_examples.sh) — 現成个 shell 範例。
* [Omi 文件](https://docs.omi.me/doc/developer/cli/introduction) — 完整个命令參考。
