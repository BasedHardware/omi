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

```bash
omi --json local task complete task_1
```
