# omi-cli cho agent

> Hướng dẫn thực hành cho các harness điều khiển bởi LLM (Claude Code, Cursor, bot của bạn).

## Vì sao CLI thân thiện với agent

* **Hợp đồng JSON ổn định.** `--json` xuất một tài liệu JSON hợp lệ ra stdout và *chỉ* JSON — không thông báo tiến trình hay spinner. Lỗi đi vào stderr dưới dạng `{"error": "...", "detail": "..."}`.
* **Mã thoát ổn định.** `0` ok / `1` usage / `2` auth / `3` server / `4` rate limited / `5` not found. Agent có thể rẽ nhánh trên chúng mà không cần phân tích lỗi ngôn ngữ tự nhiên.
* **Không có prompt tương tác trong ngữ cảnh headless.** Truyền `--yes` (hoặc `-y`) cho lệnh phá hủy; truyền `--api-key` hoặc đặt `OMI_API_KEY` để bỏ qua đăng nhập tương tác.
* **Hành vi retry khoan dung.** `429` và `5xx` được retry với backoff trước khi trồi lên.

## Xác thực (một lần, do con người)

Người dùng lấy dev API key từ ứng dụng web Omi
(`https://app.omi.me` → Developer → API Keys) rồi:

```bash
omi auth login                          # dán tương tác; key không trong lịch sử shell
# # hoặc
export OMI_API_KEY=omi_dev_...          # ngắn hạn, phù hợp container
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

### 3. Đọc conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Đọc các action item đang mở

```bash
omi action-item list --json --open
```

### 5. Đánh dấu action item hoàn thành

```bash
omi action-item complete --json a1b2c3d4
```

## API Desktop cục bộ

Khi Omi Desktop mở API cục bộ, agent có thể truy vấn lịch sử màn hình,
recap, SQL và task trên thiết bị mà không cần dev API trên đám mây:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # hoặc, cho các phiên ngắn hạn:
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

Chỉ hoàn thành hoặc xóa task khi người dùng yêu cầu rõ ràng:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ghi screenshot ra đĩa
và vẫn in JSON ra stdout cho script. Screenshot ID thường đến từ `local
search-screen` hoặc SQL trên bảng `screenshots`. Nếu Desktop trả về lỗi có cấu trúc
như `screenshot_pending`, `screenshot_file_missing` hay `screenshot_chunk_corrupted`,
chế độ JSON giữ lại `reason`, `hint` và `screenshot_id` trên stderr để agent có thể
thử lại ID cũ hơn hoặc báo đúng điểm nghẽn. Kiểm tra output thành công bằng
`file PATH` trước khi đưa cho công cụ vision.

## Ví dụ thực hành: vòng lặp agent Python

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

# Đọc tất cả action item mở và đánh dấu hoàn thành những mục cũ hơn 30 ngày.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Xử lý rate limit

Memories: 120/giờ. Conversations: 25/giờ. Tạo hàng loạt: 15/giờ.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] có dạng: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Mẹo

* Dùng `--profile <name>` nếu agent quản lý nhiều tài khoản Omi. Mỗi profile
  có credential và API base riêng.
* Dùng `--api-base http://localhost:8080` để test backend cục bộ.
* Dùng `OMI_LOCAL_API_URL` và `OMI_LOCAL_TOKEN` để ghi đè cài đặt Desktop
  API của profile cho một lần chạy.
* Dùng `--verbose` để debug — ghi `METHOD path → status (Ns)` ra stderr
  mà không ảnh hưởng stdout, nên chế độ JSON vẫn hợp lệ.
* Để pipe nội dung vào conversation, dùng `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
