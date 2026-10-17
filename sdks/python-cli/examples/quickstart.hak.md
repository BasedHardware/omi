# omi-cli 快速入門

這份指南用客家話解說基本指令。指令名稱同程式訊息維持英文。下面个範例
指令毋會改動你个記憶、對話、行動項目或者目標。

## 安裝程式

需求:Python 3.10 以上還有一隻 Omi 帳號。

假使 `pipx` 已經安裝:

```sh
pipx install omi-cli
omi --help
```

抑係安裝到已經啟動个 Python 虛擬環境:

```sh
python -m pip install omi-cli
omi --help
```

假使終端機尋毋著 `omi`,請確認虛擬環境已啟動,或者 `pipx` 安裝執行檔个
目錄有在 `PATH` 裡肚。

## 連接你个帳號

執行互動式指南:

```sh
omi auth login
```

選瀏覽器登入,抑係貼上 Omi 開發者 API key。互動式輸入會𢱤起來;毋好
寫入會留在終端機歷史紀錄个指令。

直接用瀏覽器:

```sh
omi auth login --browser
```

在同終端機共一台電腦登入,因為認證用本機 callback 位址。照螢幕上个指示做。

登入之後,檢查設定同 API 權限:

```sh
omi auth status
omi auth whoami
```

`status` 顯示本機狀態還會將密碼遮起來,但係毋會檢查佢兜在伺服器係毋係
還有效。`whoami` 送出一隻認證請求;假使成功,你个憑證就有效——毋使
顯示你个名字。

設定預設存到 `~/.omi/config.toml`。毋好分享這隻檔案,裡肚可能有憑證。

## 讀你个資料

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

空个列表可能係講無項目符合篩選條件。用 help 看每隻指令个選項:

```sh
omi memory list --help
omi action-item list --help
```

## 攞 JSON 還有分頁

全域个 `--json` 選項愛放 **指令群組頭前**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

頭一隻指令攞頭 25 筆記憶;第二隻攞接落來 25 筆。一頁毋係完整備份。JSON
輸出保留完整 ID,表格為著顯示可能會縮短 ID。

將一頁存到檔案:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

重導向會建立或者覆蓋本機檔案。使用內容進前先確認指令順利完成。錯誤寫到
stderr;空檔案毋證明無資料。匯出檔案可能有個人資訊——請私人保存。

## 用設定檔

狀態存到 `~/.omi/config.toml`(可用 `$OMI_CONFIG` 改)。每隻設定檔有自家个
認證方式同 API 位址。用 `--profile` 切換:

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

這兜離開碼穩定,適合腳本或者代理程式:

| 碼 | 意思 | 範例情況 |
| ---: | --- | --- |
| 0 | 成功 | 指令完成 |
| 1 | 用法錯誤 | 旗標毋著、欠參數,或者驗證失敗 |
| 2 | 認證錯誤 | 無憑證、token 過期,抑係權限毋罅 |
| 3 | 伺服器錯誤 | 伺服器 5xx 抑係連線失敗 |
| 4 | 速率限制 | 伺服器回 HTTP 429 |
| 5 | 尋毋著 | 伺服器回 HTTP 404 |

## 登出

```sh
omi auth logout
```

會移除本機儲存个憑證。愛在伺服器撤銷 key,請用你帳號个開發者 key 管理。

更多指令同選項請看 [英文主 README](../README.md),還有執行 `omi --help`。
