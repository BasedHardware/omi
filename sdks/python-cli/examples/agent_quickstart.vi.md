# omi-cli dành cho Agent

> Hướng dẫn thực hành cho các harness điều khiển bằng LLM (Claude Code, Cursor, bot tùy chỉnh của bạn).

## Tại sao CLI này thân thiện với Agent

* **Hợp đồng JSON ổn định.** Tuỳ chọn `--json` xuất ra tài liệu JSON hợp lệ tới stdout và *chỉ* tài liệu JSON — không có thông báo tiến trình, không có biểu tượng tải (spinner). Lỗi được chuyển tới stderr dưới dạng `{"error": "...", "detail": "..."}`.
* **Mã thoát ổn định.** `0` thành công / `1` lỗi cú pháp hoặc sử dụng / `2` lỗi xác thực / `3` lỗi máy chủ / `4` vượt giới hạn tốc độ (rate limited) / `5` không tìm thấy. Agent có thể phân nhánh logic dựa trên các mã này mà không cần phân tích lỗi bằng ngôn ngữ tự nhiên.
* **Không có lời nhắc tương tác trong môi trường headless.** Truyền `--yes` (hoặc `-y`) cho các lệnh phá hủy; truyền `--api-key` hoặc đặt biến môi trường `OMI_API_KEY` để bỏ qua bước đăng nhập tương tác.
* **Cơ chế thử lại linh hoạt.** Các lỗi `429` và `5xx` được tự động thử lại với độ trễ tăng dần (exponential backoff) trước khi trả về lỗi.

## Xác thực (một lần duy nhất, bởi con người)

Người dùng lấy khóa API dành cho nhà phát triển từ ứng dụng web Omi (`https://app.omi.me` → Developer → API Keys) và thực hiện một trong hai cách:

```bash
omi auth login                          # dán tương tác; khóa không lưu vào lịch sử shell
# hoặc
export OMI_API_KEY=omi_dev_...          # tạm thời, phù hợp cho container
```

## Năm thao tác agent thực hiện nhiều nhất

### 1. Đọc ký ức

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Tạo một ký ức

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Đọc các cuộc trò chuyện

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Đọc các mục hành động đang mở

```bash
omi action-item list --json --open
```

### 5. Đánh dấu mục hành động hoàn thành

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop cục bộ

Khi Omi Desktop mở API cục bộ, agent có thể truy vấn lịch sử màn hình, tóm tắt, SQL và tác vụ trên thiết bị mà không cần gọi API đám mây:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# hoặc cho các phiên tạm thời:
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

Lệnh `omi local screenshot SCREENSHOT_ID --output PATH` ghi ảnh chụp màn hình vào đĩa và vẫn in JSON ra stdout cho tập lệnh. ID ảnh chụp màn hình thường lấy từ `local search-screen` hoặc truy vấn SQL trên bảng `screenshots`. Nếu Desktop trả về lỗi có cấu trúc như `screenshot_pending`, `screenshot_file_missing` hoặc `screenshot_chunk_corrupted`, chế độ JSON sẽ giữ lại các trường `reason`, `hint` và `screenshot_id` trên stderr để agent có thể thử lại với ID cũ hơn hoặc báo cáo chính xác nguyên nhân chặn. Kiểm tra đầu ra thành công bằng `file PATH` trước khi chuyển sang các công cụ thị giác.

## Ví dụ thực tế: Vòng lặp Agent bằng Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Gọi omi CLI ở chế độ JSON, kích hoạt ngoại lệ khi mã thoát không thành công."""
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

# Đọc tất cả các mục hành động đang mở và đánh dấu hoàn thành mục nào cũ hơn 30 ngày.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xử lý giới hạn tốc độ

Ký ức: 120/giờ. Cuộc trò chuyện: 25/giờ. Tạo hàng loạt: 15/giờ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # vượt giới hạn tốc độ
    err = json.loads(result.stderr)
    # err["detail"] có dạng: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Lời khuyên hữu ích

* Sử dụng `--profile <name>` nếu agent của bạn quản lý nhiều tài khoản Omi. Mỗi hồ sơ có thông tin xác thực và API base riêng.
* Sử dụng `--api-base http://localhost:8080` để thử nghiệm backend cục bộ.
* Sử dụng `OMI_LOCAL_API_URL` và `OMI_LOCAL_TOKEN` để ghi đè cài đặt Desktop API cục bộ của hồ sơ cho một lần chạy.
* Sử dụng `--verbose` để gỡ lỗi — lệnh này ghi `METHOD path → status (Ns)` vào stderr mà không ảnh hưởng đến stdout, giúp chế độ JSON luôn hợp lệ.
* Để truyền nội dung qua đường ống vào cuộc trò chuyện, sử dụng `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
