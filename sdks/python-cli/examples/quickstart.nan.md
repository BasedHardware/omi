# omi-cli 快速入門（台語）

這份指南用台語說明頭一擺使用 omi-cli 个指令。指令名佮程式个訊息維持英文。這搭个範例查詢袂改變汝个 memories、conversations、action items、抑是 goals。

## 安裝

需求：Python 3.10 抑是較新个版本，佮一个 Omi 帳號。

若是汝有安裝 pipx：

```sh
pipx install omi-cli
omi --help
```

抑是安裝佇已經啟用个 Python virtual environment 內底：

```sh
python -m pip install omi-cli
omi --help
```

注意：`omi` 指令可能一開始猶毋佇汝个 PATH 面頂 — 請確定 virtual environment 有啟用，抑是 pipx 个資料夾佇 `$PATH` 內底。

## 登入

使用 CLI 進前，請先登入：

```sh
omi auth login
```

汝會使透過瀏覽器登入，嘛會使用 Omi 開發者 API key。Key 是用貼个 — 袂留佇終端機歷史內底。

佇這台電腦用瀏覽器登入：

```sh
omi auth login --browser
```

若是干焦有終端機个機器：授權會佇本地網址完成。請照螢幕頂个指示來做。

檢查目前个設定佮 API key：

```sh
omi auth status
omi auth whoami
```

`status` 會顯示本地資訊，閣會共 secrets 藏起來，袂去問伺服器。`whoami` 會送出一个有認證个請求；若成功就表示汝个 credentials 會當使用。

設定存佇 `~/.omi/config.toml`。毋好用手改這个檔案 — 內底有 key 个秘密。

## 列出 memories 佮 conversations

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

若是列表是空个，干焦表示內底猶無內容。欲知影逐个指令支援啥物 filter，會使看：

```sh
omi memory list --help
omi action-item list --help
```

## JSON 佮匯出

全域个 `--json` 選項愛囥佇 command group **頭前**：

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

頭一条指令會提頭前 25 筆 memories；第二条提接落來个 25 筆。JSON 輸出有完整个 identifier，表格顯示會共伊截短。

存落檔案：

```sh
omi --json memory list --limit 25 --offset 0 > memories-第1頁.json
```

這个重導向會建立抑是覆寫本地檔案。請先檢查指令个輸出。錯誤會去著 stderr；空檔案毋代表無資料。匯出檔案可能有個人資訊 — 請好好保護。

## 登出

```sh
omi auth logout
```

這个指令會共本地个 credentials 刪除。伺服器面頂个 key 愛佇 developer key management 管理。

欲看較多个指令佮選項：[英文文件](../README.md) 佮 `omi --help`。
