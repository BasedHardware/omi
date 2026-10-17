# omi-cli 快速上手

搿份指南用吳語講解基本命令。命令名搭程序消息仍舊是英文。下底个範例
命令勿會改動儂个記憶、對話、操作項目或者目標。

## 安裝程序

需要:Python 3.10 或以上搭一隻 Omi 賬號。

假使 `pipx` 已經裝好:

```sh
pipx install omi-cli
omi --help
```

或者裝到已經啟動个 Python 虛擬環境裡向:

```sh
python -m pip install omi-cli
omi --help
```

假使終端尋勿著 `omi`,請確認虛擬環境已經啟動,或者 `pipx` 裝執行文件个
目錄勒 `PATH` 裡向。

## 連接儂个賬號

運行交互式指南:

```sh
omi auth login
```

揀瀏覽器登錄,或者貼上 Omi 開發者 API key。交互式輸入會得將 key 隱藏;
勿要寫進會留勒終端歷史裡向个命令。

直接用瀏覽器:

```sh
omi auth login --browser
```

勒同終端一台電腦上登錄,因為認證用本機 callback 地址。照螢幕上个指示做。

登錄之後,檢查配置搭 API 訪問權:

```sh
omi auth status
omi auth whoami
```

`status` 顯示本機狀態還會得將秘密遮牢,但勿會檢查伊拉勒伺服器上還
有效勿。`whoami` 發出一隻認證請求;假使成功,儂个憑證就有效——勿必
顯示儂个名字。

配置默認存勒 `~/.omi/config.toml`。勿要分享搿隻文件,裡向可能有憑證。

## 讀儂个數據

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

空个列表可能講無項目符合篩選條件。用 help 看每隻命令个選項:

```sh
omi memory list --help
omi action-item list --help
```

## 拿 JSON 還有翻頁

全域个 `--json` 選項要放勒 **命令組前頭**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

頭一隻命令拿頭 25 筆記憶;第二隻拿跟牢个 25 筆。一頁勿是完整備份。
JSON 輸出保留完整 ID,表格為著顯示可能會縮短 ID。

將一頁存到文件:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

重定向會建立或者覆蓋本機文件。用內容之前先確認命令順利完成。錯誤寫到
stderr;空文件勿證明無數據。導出文件可能有個人信息——請私人保存。

## 用配置檔

狀態存勒 `~/.omi/config.toml`(可以用 `$OMI_CONFIG` 改)。每隻配置檔有
自家个認證方法搭 API 地址。用 `--profile` 切換:

```sh
omi config profile use 生活
omi auth login
omi --profile 私人 memory list
```

常用个配置命令:

```sh
omi config show
omi config path
omi config profile list
```

## 退出碼

搿眼退出碼穩定,適合腳本或者代理程序:

| 碼 | 意思 | 範例情況 |
| ---: | --- | --- |
| 0 | 成功 | 命令完成 |
| 1 | 用法錯誤 | 標誌勿著、缺參數,或者驗證失敗 |
| 2 | 認證錯誤 | 無憑證、token 過期,或者權限勿夠 |
| 3 | 伺服器錯誤 | 伺服器 5xx 或者連線失敗 |
| 4 | 速率限制 | 伺服器回 HTTP 429 |
| 5 | 尋勿著 | 伺服器回 HTTP 404 |

## 登出

```sh
omi auth logout
```

會得移除本機儲存个憑證。要勒伺服器上撤銷 key,請用儂賬號个開發者 key
管理。

更多命令搭選項請看 [英文主 README](../README.md),還有執行 `omi --help`。
