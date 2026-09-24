# omi-cli cho agent

> Hướng dẫn thực tế cho các harness chạy bằng LLM (Claude Code, Cursor, bot của riêng bạn).

## Vì sao CLI thân thiện với agent

* **Hợp đồng JSON ổn định.** `--json` xuất một tài JSON hợp lệ ra stdout và
  *chỉ* một tài JSON — không có tin nhắn tiến trình, không có spinner. Lỗi đưa ra
  stderr dạng `{"error": "...", "detail": "..."}`.
* **Mã thoát ổn định.** `0` ok / `1` lỗi cách dùng / `2` lỗi xác thực / `3` lỗi máy chủ / `4` bị
  giới hạn tốc độ / `5` không tìm thấy. Agent có thể rẽ nhánh theo các mã này mà không cần phân tích
  lỗi ngôn ngữ tự nhiên.
* **Không có lời nhắc tương tác trong ngữ cảnh headless.** Truyền `--yes` (hoặc `-y`) cho
  các lệnh phá hủy; truyền `--api-key` hoặc đặt `OMI_API_KEY` để bỏ qua
  đăng nhập tương tác.
* **Hành vi thử lại khoan dung.** `429` và `5xx` được thử lại với backoff
  trước khi hiển thị.

## Xác thực (một lần, do con người thực hiện)

Người dùng lấy API key nhà phát triển từ web app Omi
(`https://app.omi.me` → Developer → API Keys) và chọn một trong hai cách:

```bash
omi auth login                          # dán tương tác; key không nằm trong lịch sử shell
# hoặc
export OMI_API_KEY=omi_dev_...          # tạm thời, thân thiện với container
```

## Năm việc agent làm nhiều nhất

### 1. Đọc memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tạo một memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Đọc hội thoại

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Đọc các action item đang mở

```bash
omi action-item list --json --open
```

### 5. Đánh dấu một action item đã xong

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop cục bộ

Khi Omi Desktop mở API cục bộ, agent có thể truy vấn lịch sử màn hình
trên thiết bị, tóm tắt, SQL và task mà không dùng cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# hoặc, cho phiên tạm:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

Chỉ complete hoặc delete task khi người dùng yêu cầu rõ ràng:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ghi ảnh chụp màn hình ra
đĩa và vẫn in JSON ra stdout cho script. ID ảnh chụp thường đến từ
`local search-screen` hoặc SQL trên bảng `screenshots`. Nếu Desktop
trả về lỗi có cấu trúc như `screenshot_pending`, `screenshot_file_missing`
hoặc `screenshot_chunk_corrupted`, chế độ JSON giữ các trường `reason`, `hint` và
`screenshot_id` trên stderr để agent thử lại ID cũ hơn hoặc báo đúng
điểm chặn. Kiểm tra đầu ra thành công bằng `file PATH` trước khi đưa
cho công cụ thị giác.

## Ví dụ thực hành: vòng lặp agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Gọi omi CLI ở chế độ JSON, ném lỗi khi mã thoát khác 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI in lỗi có cấu trúc ra stderr ở chế độ JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Đọc mọi action item đang mở và complete các mục cũ hơn 30 ngày.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xử lý giới hạn tốc độ

Memories: 120/giờ. Conversations: 25/giờ. Tạo hàng loạt: 15/giờ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # bị giới hạn tốc độ
    err = json.loads(result.stderr)
    # err["detail"] trông giống: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mẹo

* Dùng `--profile <tên>` nếu agent của bạn quản lý nhiều tài khoản Omi. Mỗi
  profile có credential và API base riêng.
* Dùng `--api-base http://localhost:8080` để test backend cục bộ.
* Dùng `OMI_LOCAL_API_URL` và `OMI_LOCAL_TOKEN` để ghi đè cài đặt
  API Desktop theo profile cho một lần chạy.
* Dùng `--verbose` khi gỡ lỗi — nó ghi `METHOD path → status (Ns)` ra stderr
  không ảnh hưởng stdout, nên JSON mode vẫn hợp lệ.
* Để pipe nội dung vào hội thoại, dùng `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
