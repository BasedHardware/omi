# omi-cli cho AI Agent

> Hướng dẫn thực chiến cho các môi trường điều khiển bằng LLM (Claude Code, Cursor, hoặc bot tự động hóa riêng).

## Tại sao CLI này thân thiện với Agent

* **Giao thức JSON ổn định.** Cờ `--json` xuất ra tài liệu JSON hợp lệ tới stdout và *chỉ* tài liệu JSON duy nhất — không chứa thông báo tiến trình, không có hoạt ảnh tải (spinners). Các lỗi được chuyển hướng về stderr dưới dạng `{"error": "...", "detail": "..."}`.
* **Mã thoát (Exit codes) nhất quán.** `0` thành công / `1` sử dụng sai cú pháp / `2` lỗi xác thực / `3` lỗi máy chủ / `4` bị giới hạn tần suất (rate limited) / `5` không tìm thấy tài nguyên. Agent có thể phân nhánh logic trực tiếp dựa trên mã thoát mà không cần bóc tách ngôn ngữ tự nhiên.
* **Không yêu cầu xác nhận tương tác trong môi trường headless.** Truyền `--yes` (hoặc `-y`) cho các lệnh có tính hủy dữ liệu; truyền `--api-key` hoặc thiết lập biến môi trường `OMI_API_KEY` để bỏ qua bước đăng nhập tương tác.
* **Cơ chế thử lại linh hoạt.** Các mã lỗi `429` và `5xx` được tự động thử lại với chiến lược backoff trước khi báo lỗi ra ngoài.

## Xác thực (Một lần duy nhất, thực hiện bởi con người)

Người dùng lấy dev API key từ Omi web app (`https://app.omi.me` → Developer → API Keys) và thực hiện một trong hai cách sau:

```bash
omi auth login                          # dán key qua giao diện tương tác; key không bị lưu vào lịch sử shell
# hoặc
export OMI_API_KEY=omi_dev_...          # tạm thời, phù hợp với môi trường container
```

## 5 tác vụ Agent thường thực hiện nhất

### 1. Đọc danh sách ký ức (memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tạo một ký ức mới

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Đọc danh sách cuộc hội thoại

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Đọc các mục hành động (action items) đang mở

```bash
omi action-item list --json --open
```

### 5. Đánh dấu một mục hành động đã hoàn thành

```bash
omi action-item complete --json a1b2c3d4
```

## Local Desktop API (API Cục bộ trên Máy tính)

Khi Omi Desktop mở API cục bộ, Agent có thể truy vấn lịch sử màn hình, tóm tắt recap, cơ sở dữ liệu SQL và danh sách tác vụ trực tiếp trên thiết bị mà không cần gọi cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# hoặc dùng cho phiên làm việc tạm thời:
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

Chỉ hoàn thành hoặc xóa tác vụ khi người dùng yêu cầu rõ ràng:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Lệnh `omi local screenshot SCREENSHOT_ID --output PATH` sẽ ghi ảnh chụp màn hình ra đĩa và đồng thời xuất JSON ra stdout cho các script xử lý. ID ảnh chụp màn hình thường lấy từ `local search-screen` hoặc truy vấn SQL trên bảng `screenshots`. Nếu ứng dụng Desktop trả về lỗi có cấu trúc như `screenshot_pending`, `screenshot_file_missing`, hoặc `screenshot_chunk_corrupted`, chế độ JSON sẽ bảo toàn các trường `reason`, `hint`, và `screenshot_id` trên stderr để Agent có thể thử lại với ID cũ hơn hoặc báo cáo chính xác điểm nghẽn. Hãy kiểm tra tính hợp lệ của tệp xuất ra bằng lệnh `file PATH` trước khi chuyển sang các công cụ thị giác (vision tools).

## Ví dụ thực chiến: Vòng lặp Agent bằng Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Gọi omi CLI ở chế độ JSON, raise ngoại lệ nếu mã thoát không thành công."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI xuất lỗi có cấu trúc ra stderr ở chế độ JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Đọc toàn bộ các action items đang mở và đánh dấu hoàn thành nếu tạo quá 30 ngày trước.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xử lý giới hạn tần suất (Rate Limits)

Ký ức (Memories): 120 lần/giờ. Cuộc hội thoại (Conversations): 25 lần/giờ. Tạo hàng loạt (Batch creates): 15 lần/giờ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # bị giới hạn tần suất
    err = json.loads(result.stderr)
    # err["detail"] có dạng: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mẹo & Thực hành tốt nhất

* Sử dụng `--profile <tên>` nếu Agent của bạn quản lý nhiều tài khoản Omi khác nhau. Mỗi profile sẽ có thông tin xác thực và API base riêng biệt.
* Sử dụng `--api-base http://localhost:8080` để kiểm thử với backend cục bộ.
* Sử dụng `OMI_LOCAL_API_URL` và `OMI_LOCAL_TOKEN` để ghi đè cài đặt Desktop API của profile trong một lần chạy duy nhất.
* Sử dụng `--verbose` khi cần gỡ lỗi — cờ này sẽ ghi nhật ký `METHOD path → status (Ns)` ra stderr mà không ảnh hưởng stdout, giữ cho đầu ra JSON luôn hợp lệ.
* Để truyền trực tiếp nội dung dạng pipe vào một cuộc hội thoại, hãy dùng `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
