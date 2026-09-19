# omi-cli cho các agent

> Hướng dẫn thực tế cho môi trường điều khiển bởi LLM (Claude Code, Cursor, các bot của riêng bạn).

## Tại sao CLI thân thiện với agent

* **Hợp đồng JSON ổn định.** `--json` xuất một tài liệu JSON hợp lệ ra stdout và *chỉ* tài liệu đó — không có thông báo tiến trình hay spinner. Lỗi được ghi vào stderr dưới dạng `{"error": "...", "detail": "..."}`.
* **Mã thoát ổn định.** `0` ok / `1` lỗi sử dụng / `2` lỗi quyền / `3` lỗi máy chủ / `4` giới hạn tốc độ / `5` không tìm thấy. Agent có thể phân nhánh theo các mã này mà không cần phân tích ngôn ngữ tự nhiên trong thông báo lỗi.
* **Không có lời nhắc tương tác trong ngữ cảnh headless.** Truyền `--yes` (hoặc `-y`) cho các lệnh phá hủy; truyền `--api-key` hoặc đặt `OMI_API_KEY` để bỏ qua đăng nhập tương tác.
* **Logic thử lại khoan dung.** `429` và `5xx` được thử lại với backoff theo cấp số nhân trước khi báo cáo.

## Xác thực (một lần, bởi người dùng)

Người dùng lấy khóa API nhà phát triển từ ứng dụng web Omi (`https://app.omi.me` → Developer → API Keys) và chạy một trong hai:

```bash
omi auth login                          # dán tương tác; khóa không vào lịch sử shell
# oder / ou / ili / or / ή / veya / või / o / ale /
export OMI_API_KEY=omi_dev_...          # tạm thời, thân thiện với container
```

## Năm điều agent làm nhiều nhất

### 1. Đọc ký ức

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tạo một ký ức

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Đọc cuộc hội thoại

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Đọc các mục hành động đang mở

```bash
omi action-item list --json --open
```

### 5. Đánh dấu một mục hành động là hoàn thành

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop cục bộ

Khi Omi Desktop cung cấp API cục bộ, agent có thể truy vấn lịch sử màn hình trên thiết bị, tóm tắt, SQL và tác vụ mà không sử dụng API dev trên đám mây:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# tạm thời, thân thiện với container:
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

`omi local screenshot SCREENSHOT_ID --output PATH` lưu ảnh chụp màn hình vào đĩa và vẫn ghi JSON vào stdout cho các script. ID ảnh chụp màn hình thường đến từ `local search-screen` hoặc SQL trên bảng `screenshots`. Nếu Desktop trả về lỗi có cấu trúc như `screenshot_pending`, `screenshot_file_missing` hoặc `screenshot_chunk_corrupted`, chế độ JSON bảo toàn các trường `reason`, `hint` và `screenshot_id` trên stderr để agent có thể thử lại với ID cũ hơn hoặc báo cáo chướng ngại vật chính xác. Xác minh kết quả thành công bằng `file PATH` trước khi truyền vào các công cụ thị giác.

## Ví dụ thực tế: vòng lặp agent Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Chạy CLI omi ở chế độ JSON và ném ngoại lệ khi có mã thoát xấu."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ghi lỗi có cấu trúc vào stderr ở chế độ JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi thoát với mã {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Đọc tất cả các mục hành động đang mở và đánh dấu những mục cũ hơn 30 ngày là hoàn thành.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xử lý giới hạn tốc độ

Ký ức: 120/giờ. Cuộc hội thoại: 25/giờ. Tạo hàng loạt: 15/giờ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # giới hạn tốc độ
    err = json.loads(result.stderr)
    # err["detail"] trông như: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mẹo

* Sử dụng `--profile <tên>` nếu agent của bạn quản lý nhiều tài khoản Omi. Mỗi hồ sơ có thông tin xác thực và cơ sở API riêng.
* Sử dụng `--api-base http://localhost:8080` để kiểm tra backend cục bộ.
* Sử dụng `OMI_LOCAL_API_URL` và `OMI_LOCAL_TOKEN` để ghi đè cài đặt Desktop API của hồ sơ cho một lần chạy.
* Sử dụng `--verbose` để gỡ lỗi — ghi `METHOD path → status (Ns)` vào stderr mà không ảnh hưởng đến stdout, vì vậy chế độ JSON vẫn hợp lệ.
* Để pipe nội dung vào cuộc hội thoại, sử dụng `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
