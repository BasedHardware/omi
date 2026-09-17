# omi-cli 繁體中文快速入門

> 從終端機與 Omi 對話。專為人類和 AI Agent 設計。

`omi-cli` 是 [Omi](https://omi.me) 開發者 API 的命令列介面。
它提供面向 Agent 的指令，涵蓋 Omi 維護的四個核心資源：

* **memories** — 系統保存的事實和記憶
* **conversations** — 已捕獲並處理的對話
* **action items** — 待辦事項和跟進任務
* **goals** — 追蹤的進度指標

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **文件:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **原始碼:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. 安裝

推薦使用 `pipx` 進行隔離安裝，避免與其他 Python 套件衝突。

```bash
# 推薦方式：使用 pipx 安裝
pipx install omi-cli

# 或使用 pip 安裝
pip install omi-cli
```

> **注意：PyPI 套件名稱是 `omi-cli`，不是 `omi`。**
> * PyPI 上的發行套件名為 **`omi-cli`**（裸名 `omi` 屬於另一個無關專案）。
> * 安裝後命令列工具名為 **`omi`**。

安裝完成後，驗證：

```bash
omi --version
omi --help
```

---

## 2. 登入認證

`omi-cli` 支援兩種認證方式。

| 認證方式 | 適用場景 | 指令 |
| :--- | :--- | :--- |
| **開發者 API Key** (`omi_dev_*`) | CI/CD、自動化、Agent | `omi auth login --api-key ...` 或直接設定環境變數 |
| **瀏覽器登入** (Google/Apple) | 個人日常使用 | `omi auth login --browser` |

### 互動式登入（推薦）

如果你不確定選擇哪種方式，執行互動式登入，按提示選擇：

```bash
omi auth login
# 1) Browser → 使用 Google 或 Apple 登入（推薦人類使用者）
# 2) API key → 貼上來自 app.omi.me 的開發者金鑰（推薦 Agent/CI）
```

選擇瀏覽器登入後，會開啟瀏覽器完成 OAuth 流程。

### 瀏覽器登入

```bash
omi auth login --browser
```

### API Key 登入

從 [app.omi.me](https://app.omi.me) 取得金鑰，進入 **Developer → API Keys** 頁面。

```bash
# 互動式輸入金鑰（安全，不會回顯）
omi auth login --api-key omi_dev_...

# 或透過環境變數設定（適合 CI/CD 和自動化）
export OMI_API_KEY=omi_dev_...
```

設定 `OMI_API_KEY` 環境變數後，無需再次執行 `auth login`，
CLI 會自動使用該金鑰，無需互動式登入。適合在 CI/CD 或自動化腳本中使用。

### 檢查認證狀態

有兩個相關指令，請注意區分：

* `omi auth status` — 檢查**本機**認證狀態：是否有金鑰、是否過期等。
  不會向伺服器端發送請求。
* `omi auth whoami` — 向 Omi 伺服器端驗證**實際身份**：傳回當前金鑰對應的帳戶資訊。
  需要網路連線。

```bash
omi auth status    # 本機認證狀態，快速檢查
omi auth whoami    # 向伺服器端驗證身份
```

如果遇到金鑰過期或權限問題，重新整理認證：

```bash
omi auth refresh
```

登出：

```bash
omi auth logout
```

---

## 3. 讀取你的資料

以下指令只讀取對應資源，不會修改任何資料：

```bash
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open --limit 5
omi goal list --limit 5
```

| 指令群組 | 對應內容 |
| --- | --- |
| `memory` | 系統保存的事實和記憶 |
| `conversation` | 已捕獲並處理的對話 |
| `action-item` | 待辦事項 |
| `goal` | 目標及進度 |

列表通常只傳回一頁。需要後續頁時，先執行相應的 `list --help` 檢視該指令支援的分頁選項。

> 空結果不一定表示登入失敗；以指令的錯誤訊息和離開狀態為準。

---

## 4. 在腳本中使用 JSON 輸出

`--json` 是全域選項，放在指令群組之前：

```bash
omi --json memory list --limit 5
omi --json conversation list --limit 5
```

輸出為標準 JSON，可直接傳遞給 `jq` 或其他工具處理：

```bash
omi --json memory list | jq '.[] | {id, content}'
```

### 在 Shell 腳本中使用

```bash
# 取得最近 5 條記憶的 ID
ids=$(omi --json memory list --limit 5 | jq -r '.[].id')

# 遍歷並處理每條記憶
for id in $ids; do
  echo "Processing memory: $id"
  # 在此新增你的處理邏輯
done
```

### 在 Python 中使用

```python
import subprocess, json

result = subprocess.run(
    ["omi", "--json", "memory", "list", "--limit", "5"],
    capture_output=True, text=True
)
memories = json.loads(result.stdout)
for m in memories:
    print(m["id"], m.get("content", "")[:80])
```

---

## 5. 常見離開碼

| 離開碼 | 含義 | 建議 |
| --- | --- | --- |
| `0` | 成功 | — |
| `1` | 通用錯誤 | 檢查錯誤訊息 |
| `2` | 認證失敗 | 執行 `omi auth login` |
| `3` | 網路錯誤 | 檢查網路連線 |

---

## 更多資訊

* 完整指令參考：`omi --help` 或 `omi <command> --help`
* 官方文件：[docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* 問題回報：[GitHub Issues](https://github.com/BasedHardware/omi/issues)

---

*本快速入門由 AUTO (AI Agent) 建立。對應 bounty: Issue #13082*
