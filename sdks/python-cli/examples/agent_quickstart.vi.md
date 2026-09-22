# omi-cli dành cho AI Agent

> Hướng dẫn thực tế cho môi trường LLM (Claude Code, Cursor, bot tùy chỉnh).

## Tại sao CLI Thân thiện với Agent

* **Hợp đồng JSON Ổn định:** Cờ `--json` xuất tài liệu JSON hợp lệ sang stdout và *chỉ* JSON — không có log trạng thái hay con quay tải. Lỗi được chuyển sang stderr theo định dạng `{"error": "...", "detail": "..."}`.
* **Mã Thoát Ổn định:** `0` ok / `1` lỗi sử dụng / `2` lỗi xác thực / `3` lỗi máy chủ / `4` vượt quá giới hạn tần suất / `5` không tìm thấy. Agent có thể phân nhánh logic theo mã thoát mà không cần bóc tách chuỗi ngôn ngữ tự nhiên.
* **Không Có Lời Nhắc Tương Tác trong Chế độ Headless:** Truyền `--yes` (hoặc `-y`) cho các lệnh phá hủy; truyền `--api-key` hoặc đặt biến môi trường `OMI_API_KEY` để bỏ qua đăng nhập trình duyệt.
* **Cơ chế Thử lại Tự động:** Các mã phản hồi `429` và `5xx` được tự động thử lại với độ trễ hàm mũ trước khi trả về lỗi.

## Xác thực (Một lần bởi Người dùng)

Người dùng lấy API key nhà phát triển từ ứng dụng web Omi
(`https://app.omi.me` → Developer → API Keys), sau đó chạy:

```bash
omi auth login                          # dán tương tác; key không lưu vào lịch sử shell
# hoặc
export OMI_API_KEY=omi_dev_...          # tạm thời, lý tưởng cho container và CI/CD
```

## Năm Thao tác Phổ biến Nhất của Agent

### 1. Đọc Ký ức (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tạo Ký ức

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Đọc Cuộc trò chuyện

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Đọc Công việc Cần làm (Action Items)

```bash
omi action-item list --json --open
```

### 5. Đánh dấu Hoàn thành Công việc

```bash
omi action-item complete --json a1b2c3d4
```

## API Máy tính Cục bộ (Local Desktop API)

Khi Omi Desktop kích hoạt API cục bộ, agent có thể truy vấn lịch sử màn hình, tóm tắt, SQL và tác vụ mà không cần gọi cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# hoặc cho phiên tạm thời:
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

Chỉ hoàn thành hoặc xóa công việc khi có yêu cầu rõ ràng từ người dùng:

Chỉ hoàn thành hoặc xóa tác vụ khi người dùng yêu cầu rõ ràng:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ghi ảnh chụp màn hình vào đĩa và vẫn xuất JSON ra stdout cho tập lệnh. ID ảnh chụp màn hình thường đến từ `local search-screen` hoặc truy vấn SQL trên bảng `screenshots`. Nếu ứng dụng Desktop trả về lỗi có cấu trúc như `screenshot_pending`, `screenshot_file_missing`, hoặc `screenshot_chunk_corrupted`, chế độ JSON giữ lại các trường `reason`, `hint`, và `screenshot_id` trên stderr để các agent có thể thử lại với ID cũ hơn hoặc báo cáo nguyên nhân chính xác. Xác thực kết quả thành công bằng `file PATH` trước khi chuyển sang các công cụ thị giác.

## Ví dụ thực tế: Vòng lặp Agent bằng Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xử lý giới hạn tốc độ (Handling rate limits)

Ký ức: 120/giờ. Cuộc trò chuyện: 25/giờ. Tạo hàng loạt: 15/giờ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mẹo hữu ích (Tips)

* Sử dụng `--profile <tên>` nếu agent của bạn quản lý nhiều tài khoản Omi. Mỗi hồ sơ có thông tin xác thực và API base riêng.
* Sử dụng `--api-base http://localhost:8080` để kiểm tra với backend cục bộ.
* Sử dụng `OMI_LOCAL_API_URL` và `OMI_LOCAL_TOKEN` để ghi đè cài đặt Desktop API của hồ sơ cho một lần chạy.
* Sử dụng `--verbose` để gỡ lỗi — cờ này ghi nhật ký `METHOD path → status (Ns)` ra stderr mà không ảnh hưởng stdout, do đó định dạng JSON vẫn hợp lệ.
* Để truyền nội dung vào cuộc trò chuyện qua đường ống (pipe), sử dụng `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
