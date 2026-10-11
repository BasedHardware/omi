# omi-cli 廣東話快速上手指南

呢份指南用廣東話解釋初學者嘅基礎指令。指令名稱同程式輸出訊息保持英文。呢度展示嘅查詢範例唔會修改你嘅記憶、對話、任務或者目標。

## 安裝程式

系統需求：Python 3.10 或以上版本，以及一個 Omi 帳號。

如果你有裝 `pipx`：

```sh
pipx install omi-cli
omi --help
```

或者，你亦都可以喺已啟動嘅 Python 虛擬環境入面安裝：

```sh
python -m pip install omi-cli
omi --help
```

如果終端機搵唔到 `omi`，請檢查虛擬環境係咪已經啟動，或者 `pipx` 安裝路徑係咪已經加入咗去你嘅 `PATH` 環境變數。

## 連接你嘅帳號

你可以用網頁瀏覽器登入，或者直接使用 API token。

### 方法一：用瀏覽器登入

執行以下指令：

```sh
omi auth login
```

瀏覽器會自動彈出。登入你嘅帳號並授權，終端機就會保存登入憑證。

### 方法二：使用 API Key

如果你已經喺網頁後台複製咗 token：

```sh
omi auth login --api-key <key>
```

根據提示貼上你嘅 API Key (app.omi.me -> Developer -> API Keys)。

如需喺指令碼或者臨時工作流程入面使用，可以設置環境變數：

```sh
export OMI_API_KEY="your-token-here"
```

檢查連線狀態同埋你嘅使用者名稱：

```sh
omi auth whoami
```

如果終端機顯示你嘅使用者名稱，代表連線成功。

## 查詢你嘅資料

連線完成之後，你可以開始查詢自己嘅資料。預設指令係唯讀性質，唔會修改任何內容。

### 查看最近對話

```sh
omi conversation list
```

列出最近嘅對話記錄。如需查看特定對話嘅詳細內容，請使用該對話嘅 ID：

```sh
omi conversation get <conversation-id>
```

### 查看儲存嘅記憶

```sh
omi memory list
```

列出最近保存嘅記憶項目。如需查看單一記憶項目：

```sh
omi memory get <memory-id>
```

### 查看行動任務與目標

列出待辦事項：

```sh
omi action-item list
```

列出設定嘅個人目標：

```sh
omi goal list
```

## 取得 JSON 資料並進行分頁瀏覽

所有 `list` 指令都支援 `--json` 參數，方便搭配其他工具（例如 `jq`）處理資料。

取得原始 JSON 格式輸出：

```sh
omi --json conversation list
omi --json memory list
```

使用分頁限制輸出筆數：

```sh
omi conversation list --limit 5
omi memory list --limit 10
```

如果結果超過一頁，可以配合 `--offset` 翻頁：

```sh
omi memory list --limit 10 --offset 10
```

## 登出帳號

當你喺共用電腦上完成工作，可以刪除本機憑證：

```sh
omi auth logout
```

如果之前有設置過 `OMI_API_KEY` 環境變數，亦請記得清除：

```sh
unset OMI_API_KEY
```
