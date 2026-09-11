# Hướng dẫn bắt đầu nhanh omi-cli bằng tiếng Việt

> Hướng dẫn thực hành tương tác với Omi từ dòng lệnh. Thiết kế dành cho nhà phát triển và các tác tử trí tuệ nhân tạo (AI agents).

`omi-cli` là giao diện dòng lệnh chính thức để làm việc với API nhà phát triển của [Omi](https://omi.me). Công cụ này giúp bạn truy vấn và quản lý 4 tài nguyên cốt lõi mà Omi duy trì: ký ức (memories), cuộc trò chuyện (conversations), việc cần làm (action items) và mục tiêu (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Tài liệu chính thức:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Mã nguồn:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Cài đặt

Cách cài đặt được khuyến nghị là sử dụng `pipx` để cô lập môi trường và các gói phụ thuộc:

```bash
# Khuyến nghị: cài đặt cô lập với pipx
pipx install omi-cli

# Hoặc cài đặt qua pip thông thường
pip install omi-cli
```

> **Lưu ý quan trọng: Tên gói cài đặt và Tên câu lệnh**
> * Tên gói trên PyPI là **`omi-cli`** (tên `omi` đơn lẻ thuộc về một dự án khác).
> * Câu lệnh thực thi trong terminal sau khi cài đặt là **`omi`**.

Kiểm tra cài đặt:

```bash
omi --version
omi --help
```

---

## 2. Xác thực (Authentication)

`omi-cli` hỗ trợ 2 phương thức xác thực:

| Phương thức | Trường hợp sử dụng | Ví dụ lệnh |
| :--- | :--- | :--- |
| **Khóa API Nhà phát triển (`omi_dev_*`)** | CI/CD, kịch bản tự động, tác tử AI | `omi auth login --api-key ...` hoặc biến môi trường |
| **OAuth qua Trình duyệt (Google / Apple)** | Người dùng làm việc trên máy tính cá nhân | `omi auth login --browser` |

### Đăng nhập tương tác
Nếu chạy lệnh không kèm tham số, một bảng chọn tương tác sẽ xuất hiện:

```bash
omi auth login
# 1) Browser — Đăng nhập bằng tài khoản Google hoặc Apple trên trình duyệt
# 2) API key — Dán khóa API nhà phát triển từ app.omi.me
```

### Đăng nhập trực tiếp qua trình duyệt
```bash
omi auth login --browser
```

### Đăng nhập bằng khóa API
Lấy khóa tại [app.omi.me](https://app.omi.me) trong mục «Developer → API Keys»:

```bash
# Cấu hình qua câu lệnh
omi auth login --api-key omi_dev_...

# Hoặc thiết lập biến môi trường (phù hợp với CI/CD và Docker)
export OMI_API_KEY=omi_dev_...
```

### Kiểm tra trạng thái xác thực
* `omi auth status`: Hiển thị hồ sơ đang hoạt động, thông tin đăng nhập đã che và thời hạn (hoạt động ngoại tuyến).
* `omi auth whoami`: Gửi yêu cầu kiểm tra tới máy chủ Omi để xác minh thông tin đăng nhập hợp lệ (cần kết nối mạng).

```bash
omi auth status
omi auth whoami
```

Đăng xuất và xóa thông tin xác thực trên máy:
```bash
omi auth logout
```

---

## 3. Sử dụng cơ bản

### Ký ức (Memories)
Thông tin và kiến thức hệ thống đã ghi nhận về người dùng.

```bash
# Xem danh sách ký ức
omi memory list

# Tạo một ký ức mới
omi memory create "Người dùng thích giao diện tối" --category lifestyle

# Xem chi tiết một ký ức theo ID
omi memory get <ID_KY_UC>
```

### Cuộc trò chuyện (Conversations)
Lịch sử trao đổi âm thanh và văn bản được ghi nhận bởi thiết bị Omi hoặc ứng dụng.

```bash
# Xem 5 cuộc trò chuyện gần nhất
omi conversation list --limit 5

# Xem chi tiết kèm bản ghi chép đầy đủ
omi conversation get <ID_TRO_CHUYEN> --include-transcript
```

### Việc cần làm (Action Items)
Nhiệm vụ và việc theo dõi được trích xuất tự động từ các cuộc trò chuyện.

```bash
# Chỉ hiển thị các việc chưa hoàn thành
omi action-item list --open

# Đánh dấu hoàn thành một việc
omi action-item complete <ID_HANH_DONG>
```

### Mục tiêu (Goals)
Các chỉ số và mục tiêu đang theo dõi tiến độ.

```bash
# Liệt kê các mục tiêu
omi goal list
```

---

## 4. Tự động hóa và định dạng JSON (`--json`)

`omi-cli` tích hợp sẵn khả năng xuất dữ liệu định dạng JSON để dễ dàng kết hợp với `jq` hoặc mã nguồn Python. Đặt tùy chọn `--json` ở vị trí **tùy chọn toàn cục trước câu lệnh con**:

```bash
# Lấy danh sách ký ức dưới dạng JSON
omi --json memory list | jq '.[] | {id, content, category}'

# Lấy tiêu đề các cuộc trò chuyện gần đây
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Xem danh sách việc cần làm dưới dạng JSON
omi --json action-item list --open | jq '.'
```

> **Lưu ý:** Luôn đặt `--json` **trước** lệnh con (`memory`, `conversation`, v.v.):
> * Đúng: `omi --json memory list`
> * Sai: `omi memory list --json`

---

## 5. Mã thoát (Exit Codes)

Hỗ trợ kiểm tra điều kiện trong kịch bản shell hoặc hệ thống CI/CD:

| Mã | Ý nghĩa | Mô tả |
| :---: | :--- | :--- |
| `0` | Thành công (Success) | Lệnh thực thi thành công |
| `1` | Lỗi sử dụng lệnh (Usage Error) | Tham số hoặc tùy chọn không hợp lệ |
| `2` | Lỗi xác thực (Auth Error) | Chưa đăng nhập, khóa không hợp lệ hoặc hết hạn |
| `3` | Lỗi máy chủ / mạng (Server Error) | Lỗi 5xx, quá thời gian chờ hoặc đứt kết nối mạng |
| `4` | Giới hạn tần suất (Rate Limited) | HTTP 429 Too Many Requests |
| `5` | Không tìm thấy (Not Found) | HTTP 404 (ID không tồn tại) |

---

## 6. Thiết lập biến môi trường theo từng Shell

### Bash / Zsh (Linux / macOS)
```bash
# Thiết lập khóa API
export OMI_API_KEY="omi_dev_khoa_cua_ban_o_day"

# Thực thi lệnh với xuất dữ liệu JSON
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# Thiết lập khóa API
$env:OMI_API_KEY = "omi_dev_khoa_cua_ban_o_day"

# Xử lý dữ liệu JSON trong PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. Tích hợp với Omi Desktop cục bộ

Khi ứng dụng Omi Desktop đang chạy trên máy tính, bạn có thể truy vấn lịch sử màn hình và cơ sở dữ liệu SQLite cục bộ mà không cần đi qua dịch vụ đám mây:

```bash
# Cấu hình địa chỉ và token cục bộ
omi local configure --url http://127.0.0.1:47778 --token TOKEN_DESKTOP_CUA_BAN

# Kiểm tra trạng thái kết nối cục bộ
omi --json local status

# Tìm kiếm trong lịch sử màn hình
omi --json local search-screen "hóa đơn" --days 7 --app Safari
```

---

## 8. Quản lý hồ sơ (Profiles)

Nếu bạn sử dụng nhiều tài khoản hoặc môi trường khác nhau (như cá nhân và công việc), hãy sử dụng tùy chọn `--profile`. Cấu hình được lưu trữ tại `~/.omi/config.toml`:

```bash
# Đăng nhập vào hồ sơ cá nhân
omi --profile personal auth login

# Đăng nhập vào hồ sơ công việc
omi --profile work auth login

# Chạy lệnh với hồ sơ mong muốn
omi --profile work memory list
```
