# omi-cli — hướng dẫn nhanh bằng tiếng Việt

> Hướng dẫn thực hành làm việc với Omi từ terminal. Phù hợp cho cả con người lẫn AI agent.

`omi-cli` là giao diện dòng lệnh chính thức cho API dành cho nhà phát triển của [Omi](https://omi.me).
Nó cho phép truy cập nhanh, dễ viết script tới bốn thực thể chính của Omi:
memories (ký ức), conversations (hội thoại), action items (việc cần làm) và goals (mục tiêu).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Tài liệu:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Mã nguồn:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Cài đặt

Cách được khuyến nghị là `pipx`: nó cài tiện ích vào một môi trường cô lập,
nên các phụ thuộc của nó sẽ không xung đột với các dự án của bạn.

```bash
# khuyến nghị: cài qua pipx
pipx install omi-cli

# hoặc qua pip
pip install omi-cli
```

> **Lưu ý: tên gói và tên lệnh khác nhau.**
> * Gói được cài là **`omi-cli`** (gói riêng `omi` là một dự án khác, không liên quan).
> * Sau khi cài, lệnh chạy là **`omi`**.

Kiểm tra cài đặt:

```bash
omi --version
omi --help
```

---

## 2. Xác thực

`omi-cli` hỗ trợ hai cách đăng nhập.

| Cách | Khi nào phù hợp | Lệnh |
| :--- | :--- | :--- |
| **Developer key (`omi_dev_*`)** | CI/CD, script, AI agent | `omi auth login --api-key ...` hoặc biến môi trường |
| **Đăng nhập qua trình duyệt (Google/Apple)** | Làm việc trên máy cá nhân | `omi auth login --browser` |

### Đăng nhập tương tác

Không có flag nào, lệnh sẽ tự hỏi bạn muốn đăng nhập theo cách nào:

```bash
omi auth login
# 1) Browser — đăng nhập qua Google hoặc Apple (tiện cho con người)
# 2) API key — dán developer key từ app.omi.me (tiện cho agent và CI)
```

Khi chọn API key, phần nhập sẽ bị che nên key không lưu lại trong lịch sử terminal.

### Thẳng qua trình duyệt

```bash
omi auth login --browser
```

### Bằng developer key

Lấy key tại [app.omi.me](https://app.omi.me) trong mục **Developer → API Keys**.

```bash
# lưu key vào cấu hình
omi auth login --api-key omi_dev_...

# hoặc truyền qua môi trường — nên dùng cho CI/CD và container
export OMI_API_KEY=omi_dev_...
```

Biến `OMI_API_KEY` được dùng khi profile đang hoạt động chưa lưu key,
nên trong container bạn không cần ghi gì ra đĩa. Nếu profile đã có key,
key đó sẽ được ưu tiên hơn biến môi trường.

### Kiểm tra đăng nhập

Hai lệnh trả lời hai câu hỏi khác nhau, đừng nhầm lẫn:

* `omi auth status` — xem cái gì đang nằm **trên máy**: profile, key bị che, hạn dùng.
  Chạy được không cần mạng.
* `omi auth whoami` — gọi **tới server Omi**: kiểm tra key có thực sự
  được chấp nhận không. Cần mạng.

```bash
omi auth status    # kiểm tra cục bộ, offline
omi auth whoami    # kiểm tra trên server
```

Làm mới token sắp hết hạn mà không cần đăng nhập lại:

```bash
omi auth refresh
```

Đăng xuất:

```bash
omi auth logout
```

---

## 3. Các lệnh chính

### Memories (ký ức)

Những sự kiện và kiến thức hệ thống đã ghi nhớ về bạn.

```bash
# liệt kê memories
omi memory list

# tạo mới
omi memory create "Người dùng thích giao diện tối" --category lifestyle

# xem một memory cụ thể
omi memory get <MEMORY_ID>
```

### Conversations (hội thoại)

Lịch sử lời nói và văn bản từ thiết bị hoặc từ ứng dụng.

```bash
# 5 hội thoại gần nhất
omi conversation list --limit 5

# toàn bộ hội thoại kèm bản ghi
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Action items (việc cần làm)

Những việc Omi trích ra từ các hội thoại.

```bash
# chỉ những việc chưa xong
omi action-item list --open

# đánh dấu đã hoàn thành
omi action-item complete <ACTION_ITEM_ID>
```

### Goals (mục tiêu)

```bash
# liệt kê mục tiêu
omi goal list

# ghi giá trị tiến độ mới (cần CẢ HAI tham số: mục tiêu và giá trị)
omi goal progress <GOAL_ID> 25

# lịch sử thay đổi
omi goal history <GOAL_ID>
```

---

## Hỏi bằng ngôn ngữ tự nhiên (`ask`)

Lệnh cấp cao riêng: đặt câu hỏi bằng ngôn ngữ thường,
câu trả lời được dựng từ chính các hội thoại của bạn.

```bash
omi ask "tôi đã quyết định gì về việc chuyển nhà"
omi --json ask "tuần này tôi hứa hoàn thành những việc gì"
```

---

## 4. JSON và script (`--json`)

`omi-cli` có thể trả về JSON máy đọc được. Flag `--json` là **toàn cục**,
nên phải đặt **trước** lệnh con.

```bash
# memories: lấy id, nội dung và category
omi --json memory list | jq '.[] | {id, content, category}'

# tiêu đề các hội thoại gần nhất
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# các việc chưa xong
omi --json action-item list --open | jq '.'
```

> **Lỗi thường gặp.** `--json` đi trước lệnh con, không phải sau.
> * Đúng: `omi --json memory list`
> * Sai: `omi memory list --json`

Ở chế độ `--json`, standard output chỉ chứa JSON —
script có thể dựa vào điều đó.

---

## 5. Exit code

Các mã này ổn định, nên có thể dùng để rẽ nhánh logic trong script và CI.

| Mã | Ý nghĩa | Khi nào xảy ra |
| :---: | :--- | :--- |
| `0` | Thành công | Lệnh chạy xong |
| `1` | Lỗi gọi lệnh | Flag sai, thiếu tham số |
| `2` | Lỗi truy cập | Chưa đăng nhập, key sai hoặc hết hạn |
| `3` | Lỗi server | Phản hồi 5xx, timeout, mất kết nối |
| `4` | Quá nhiều request | 429 Too Many Requests |
| `5` | Không tìm thấy | 404, id được chỉ định không tồn tại |

Ví dụ kiểm tra trong Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "key hoạt động"
else
  code=$?
  [ "$code" -eq 2 ] && echo "cần đăng nhập lại"
  [ "$code" -eq 3 ] && echo "server không truy cập được, thử lại sau"
fi
```

---

## 6. Biến môi trường

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_key_cua_ban"

omi --json memory list --limit 10
```

Để key được nạp trong các phiên mới, thêm dòng đó vào `~/.bashrc` hoặc `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_key_cua_ban"

# phân tích JSON bằng PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Cài đặt vĩnh viễn:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_key_cua_ban", "User")
```

---

## 7. Ứng dụng Omi Desktop chạy local

Nếu ứng dụng desktop Omi đang chạy, một phần dữ liệu có thể truy cập trực tiếp,
không qua cloud.

```bash
# chỉ định địa chỉ API local
omi local configure --url http://127.0.0.1:47778 --token TOKEN_CUA_BAN

# kiểm tra nó có phản hồi không
omi --json local status

# tìm trong lịch sử màn hình
omi --json local search-screen "bảng giá" --days 7 --app Safari

# chụp màn hình theo id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# truy vấn SQL tùy ý trên database local
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Quy trình làm việc: trước tiên `local status`, rồi `local tools` — để biết các
công cụ khả dụng và tham số của chúng — sau đó mới gọi.

---

## 8. Profiles

Nếu có nhiều tài khoản hoặc môi trường, hãy tách bằng profiles.
Cấu hình lưu trong `~/.omi/config.toml`.

```bash
# đăng nhập profile cá nhân
omi --profile personal auth login

# đăng nhập profile công việc
omi --profile work auth login

# chạy lệnh trong một profile cụ thể
omi --profile work memory list
```

Xem và sửa chính cấu hình:

```bash
# đang cấu hình gì
omi config show

# file cấu hình nằm đâu
omi config path

# đổi một giá trị
omi config set api_base https://api.omi.me
```

---

## 9. Bước tiếp theo

* [`agent_quickstart.md`](./agent_quickstart.md) — cách nối `omi-cli` với một AI agent.
* [`shell_examples.sh`](./shell_examples.sh) — các ví dụ shell chạy được.
* [Tài liệu Omi](https://docs.omi.me/doc/developer/cli/introduction) — tham chiếu đầy đủ các lệnh.
