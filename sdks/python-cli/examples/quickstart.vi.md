# Bắt đầu với omi-cli

Tài liệu này giải thích các lệnh cơ bản bằng tiếng Việt. Tên lệnh và thông báo
của chương trình vẫn giữ nguyên bằng tiếng Anh. Các ví dụ truy vấn ở đây không
làm thay đổi ký ức, cuộc trò chuyện, công việc hay mục tiêu của bạn.

## Cài đặt chương trình

Yêu cầu: Python 3.10 trở lên và tài khoản Omi.

Nếu bạn đã cài đặt `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ngoài ra, bạn có thể cài đặt trong môi trường ảo Python đã kích hoạt:

```sh
python -m pip install omi-cli
omi --help
```

Nếu terminal không tìm thấy `omi`, hãy kiểm tra xem môi trường ảo đã được kích hoạt
chưa hoặc thư mục mà `pipx` cài đặt file thực thi đã có trong `PATH` của bạn chưa.

## Kết nối tài khoản của bạn

Khởi chạy trình hướng dẫn tương tác:

```sh
omi auth login
```

Chọn đăng nhập qua trình duyệt hoặc dán API key dành cho nhà phát triển Omi.
Đầu vào tương tác sẽ ẩn key; tránh viết key trong lệnh vì nó sẽ lưu lại trong lịch sử terminal.

Để chuyển trực tiếp đến trình duyệt:

```sh
omi auth login --browser
```

Đăng nhập trên cùng một máy tính đang chạy terminal: phản hồi xác thực sử dụng
địa chỉ cục bộ. Làm theo hướng dẫn hiển thị trên màn hình.

Sau đó, xác minh cấu hình và quyền truy cập API:

```sh
omi auth status
omi auth whoami
```

`status` hiển thị trạng thái cục bộ và ẩn khóa bí mật, nhưng không kiểm tra tính hợp lệ trên server.
`whoami` gửi một yêu cầu đã xác thực; nếu thành công, nó xác nhận thông tin đăng nhập hoạt động mà không nhất thiết phải hiển thị tên của bạn.

Cấu hình được lưu mặc định tại `~/.omi/config.toml`. Không chia sẻ file này:
nó có thể chứa thông tin xác thực bảo mật của bạn.

## Xem dữ liệu của bạn

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Danh sách trống có thể chỉ đơn giản là không có mục nào khớp với truy vấn.
Sử dụng trợ giúp để xem các bộ lọc của từng lệnh:

```sh
omi memory list --help
omi action-item list --help
```

## Lấy định dạng JSON và phân trang

Đặt tùy chọn toàn cục `--json` **trước** nhóm lệnh:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Lệnh đầu tiên yêu cầu 25 ký ức đầu tiên; lệnh thứ hai yêu cầu 25 ký ức tiếp theo.
Do đó, một trang đơn lẻ không phải là bản sao lưu đầy đủ. Đầu ra JSON giữ nguyên các ID đầy đủ, trong khi bảng hiển thị có thể rút ngắn chúng.

Để lưu một trang vào file:

```sh
omi --json memory list --limit 25 --offset 0 > ky-uc-trang-1.json
```

Chuyển hướng này tạo hoặc ghi đè file cục bộ. Hãy chắc chắn rằng lệnh đã hoàn tất thành công trước khi sử dụng nội dung.
Lỗi được ghi vào đầu ra lỗi (stderr); file trống không đảm bảo rằng không có dữ liệu. File xuất ra có thể chứa thông tin cá nhân: hãy giữ nó riêng tư.

## Đăng xuất (Logout)

```sh
omi auth logout
```

Lệnh này xóa thông tin xác thực được lưu cục bộ. Để thu hồi key trên server,
hãy sử dụng trang quản lý developer keys trên tài khoản của bạn.

Đối với các lệnh khác và tùy chọn nâng cao, hãy xem [hướng dẫn chính bằng tiếng Anh](../README.md) và `omi --help`.
