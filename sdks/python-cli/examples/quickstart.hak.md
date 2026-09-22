# omi-cli 快速上手（客家話）

這份指南用客話解說頭一擺使用 omi-cli 个指令。指令名仔同程式訊息保持英文。這裡个範例查詢毋會改動你个 memories、conversations、action items 或者 goals。

## 安裝

需求：Python 3.10 或者更新个版本，同一個 Omi 帳號。

若是你有安裝 pipx：

```sh
pipx install omi-cli
omi --help
```

或者安裝在已經激活个 Python virtual environment 裡背：

```sh
python -m pip install omi-cli
omi --help
```

注意：`omi` 指令可能開始還毋在你个 PATH 裡背 — 請確定 virtual environment 激活咧，或者 pipx 个資料夾在 `$PATH` 裡背。

## 登入

使用 CLI 之前，請先登入：

```sh
omi auth login
```

你可以用瀏覽器登入，乜可以用 Omi 開發者 API key。Key 係貼入去个 — 毋會留在終端機歷史裡背。

在這台電腦用瀏覽器登入：

```sh
omi auth login --browser
```

假使係淨有終端機个機器：授權會在本地網址完成。請照畫面上个指示來做。

檢查這下个設定同 API key：

```sh
omi auth status
omi auth whoami
```

`status` 會顯示本地資訊，還會摝 secrets 囥起來，毋會去問伺服器。`whoami` 會送出一隻認證過个請求；成功个話，即係你个 credentials 做得用。

設定存咧 `~/.omi/config.toml`。毋好用手改這隻檔案 — 裡背有 key 个秘密。

## 列出 memories 同 conversations

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

假使列表係空个，淨係表示裡背還無內容。想知逐隻指令支援麼个 filter，做得看：

```sh
omi memory list --help
omi action-item list --help
```

## JSON 同匯出

全域个 `--json` 選項愛囥在 command group **頭前**：

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

頭一條指令會提頭前 25 筆 memories；第二條提接下來个 25 筆。JSON 輸出有完整个 identifier，表格顯示會摝佢截短。

存到檔案裡背：

```sh
omi --json memory list --limit 25 --offset 0 > memories-第1頁.json
```

這隻重導向會建立或者覆寫本地檔案。請先檢查指令个輸出。錯誤會去著 stderr；空檔案毋代表無資料。匯出檔案可能有個人資料 — 請好好保護。

## 登出

```sh
omi auth logout
```

這隻指令會摝本地个 credentials 刪除。伺服器上个 key 愛在 developer key management 管理。

想看較多个指令同選項：[英文文件](../README.md) 同 `omi --help`。
