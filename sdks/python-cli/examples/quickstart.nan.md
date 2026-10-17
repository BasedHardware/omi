# omi-cli 緊開始

這份指南用閩南話解說基本指令。指令名佮程式訊息保持英文。下跤个範例
指令袂改變你个記憶、對話、行動項目抑是目標。

## 安裝程式

需要:Python 3.10 以上佮一个 Omi 帳號。

假使 `pipx` 已經安裝:

```sh
pipx install omi-cli
omi --help
```

抑是安裝入已經啟動个 Python 虛擬環境:

```sh
python -m pip install omi-cli
omi --help
```

假使終端機揣無 `omi`,請確認虛擬環境已經啟動,抑是 `pipx` 安裝執行檔个
目錄有佇 `PATH` 內底。

## 連接你个帳號

執行互動式指南:

```sh
omi auth login
```

選瀏覽器登入,抑是貼上 Omi 開發者 API key。互動式輸入會將 key 崁起來;
毋通寫入會留佇終端機歷史个指令。

直接用瀏覽器:

```sh
omi auth login --browser
```

佇同終端機一台電腦登入,因為認證用在地 callback 位址。照螢幕頂个指示做。

登入了後,檢查設定佮 API 權限:

```sh
omi auth status
omi auth whoami
```

`status` 顯示在地狀態閣會將密碼崁起來,毋過袂檢查佢个佇伺服器閣有效無。
`whoami` 送出一个認證請求;假使成功,你个憑證就有效——毋免顯示你个名。

設定預設存佇 `~/.omi/config.toml`。毋通分享這个檔案,內底可能有憑證。

## 讀你个資料

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

空个列表可能講無項目符合篩選條件。用 help 看逐个指令个選項:

```sh
omi memory list --help
omi action-item list --help
```

## 提 JSON 閣有翻頁

全域个 `--json` 選項愛放佇 **指令群組頭前**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

頭一个指令提頭 25 筆記憶;第二个提落來个 25 筆。一頁毋是完整備份。JSON
輸出保留完整 ID,表格為著顯示可能會縮短 ID。

共一頁存落檔案:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

重導向會建立抑是覆蓋在地檔案。用內容進前先確認指令順利完成。錯誤寫到
stderr;空檔案袂證明無資料。匯出檔案可能有個人資訊——請私人保存。

## 用設定檔

狀態存佇 `~/.omi/config.toml`(會使以 `$OMI_CONFIG` 改)。逐个設定檔有
自家个認證方式佮 API 位址。用 `--profile` 切換:

```sh
omi config profile use 頭路
omi auth login
omi --profile 私人 memory list
```

常用个設定指令:

```sh
omi config show
omi config path
omi config profile list
```

## 離開碼

這兜離開碼穩定,適合腳本抑是代理程式:

| 碼 | 意思 | 範例情況 |
| ---: | --- | --- |
| 0 | 成功 | 指令完成 |
| 1 | 用法錯誤 | 旗標毋著、欠參數,抑是驗證失敗 |
| 2 | 認證錯誤 | 無憑證、token 過期,抑是權限袂罅 |
| 3 | 伺服器錯誤 | 伺服器 5xx 抑是連線失敗 |
| 4 | 速率限制 | 伺服器回 HTTP 429 |
| 5 | 揣無 | 伺服器回 HTTP 404 |

## 登出

```sh
omi auth logout
```

會移除在地儲存个憑證。欲佇伺服器撤銷 key,請用你帳號个開發者 key 管理。

閣較多指令佮選項請看 [英文主 README](../README.md),閣有執行 `omi --help`。
