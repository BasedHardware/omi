# omi-cli 快薜起手

呢份指南用壯話解說基本指令。指令名佮程式信息維持英文。下頭个範例
指令毋會改動你个記事、對話、行動項目抑是目標。

## 安裝程式

要求:Python 3.10 以上佮一個 Omi 帳號。

若果 `pipx` 已經裝好:

```sh
pipx install omi-cli
omi --help
```

抑係裝到已經啟動个 Python 虛擬環境:

```sh
python -m pip install omi-cli
omi --help
```

若果終端機尋無 `omi`,請檢查虛擬環境係咪啟動,抑係 `pipx` 裝執行檔个
目錄有冇佇 `PATH` 裡頭。

## 連接你个帳號

運行互動指南:

```sh
omi auth login
```

揀瀏覽器登入,抑係貼上 Omi 開發者 API key。互動輸入會將 key 收埋;
毋好寫入會留佇終端機歷史个指令。

直接用瀏覽器:

```sh
omi auth login --browser
```

佇同終端機一台電腦登入,因為認證用本地 callback 地址。照屏幕上个指示做。

登入之後,檢查設定佮 API 權限:

```sh
omi auth status
omi auth whoami
```

`status` 顯示本地狀態還會將密碼收埋,但毋會檢查佢个佇服務器上邊有效無。
`whoami` 發出一個認證請求;若果成功,你个憑證就有效——毋使顯示你个名。

設定預設存佇 `~/.omi/config.toml`。毋好分享呢個文件,裡頭可能有憑證。

## 讀你个數據

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

空个列表可能係講無項目符合篩選條件。用 help 睇逐个指令个選項:

```sh
omi memory list --help
omi action-item list --help
```

## 攞 JSON 還有翻頁

全域个 `--json` 選項要放佇 **指令群組前頭**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

頭一個指令攞頭 25 條記事;第二個攞跟住个 25 條。一頁毋係完整備份。JSON
輸出保留完整 ID,表格為著顯示可能會縮短 ID。

將一頁存落文件:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

重定向會建立抑係覆蓋本地文件。用內容之前先確認指令順利完成。錯誤寫到
stderr;空文件毋證明無數據。導出文件可能有個人信息——請私人保存。

## 用配置檔

狀態存佇 `~/.omi/config.toml`(可以用 `$OMI_CONFIG` 改)。逐个配置檔有
自家个認證方法佮 API 地址。用 `--profile` 切換:

```sh
omi config profile use 工作
omi auth login
omi --profile 私人 memory list
```

常用个配置指令:

```sh
omi config show
omi config path
omi config profile list
```

## 退出碼

呢兜退出碼穩定,適合腳本抑係代理程序:

| 碼 | 意思 | 範例情況 |
| ---: | --- | --- |
| 0 | 成功 | 指令完成 |
| 1 | 用法錯誤 | 標誌毋著、缺參數,抑係驗證失敗 |
| 2 | 認證錯誤 | 無憑證、token 過期,抑係權限毋夠 |
| 3 | 服務器錯誤 | 服務器 5xx 抑係連線失敗 |
| 4 | 速率限制 | 服務器回 HTTP 429 |
| 5 | 尋無 | 服務器回 HTTP 404 |

## 登出

```sh
omi auth logout
```

會移除本地儲存个憑證。要佇服務器上撤銷 key,請用你帳號个開發者 key 管理。

更多指令佮選項請睇 [英文主 README](../README.md),還有執行 `omi --help`。
