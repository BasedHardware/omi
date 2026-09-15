# Hướng dẫn bắt đầu nhanh omi-cli

## Cài đặt

```bash
pip install omi-cli
```

## Đăng nhập

```bash
omi auth login
```

Trình duyệt sẽ mở ra để bạn đăng nhập bằng tài khoản của mình.

## Các lệnh cơ bản

### Xem danh sách hội thoại

```bash
omi conversation list
```

### Xem một hội thoại cụ thể

```bash
omi conversation get <id_hội_thoại>
```

### Tìm kiếm hội thoại

```bash
omi conversation search "từ khóa tìm kiếm"
```

## Tùy chọn nâng cao

### Giới hạn số lượng

```bash
omi conversation list --limit 10
```

### Bao gồm bản ghi âm

```bash
omi conversation list --include-transcript
```

### Xuất ra định dạng JSON

```bash
omi conversation list --json
```

### Phân trang

```bash
omi conversation list --limit 50 --offset 100
```

## Đăng xuất

```bash
omi auth logout
```

## Trợ giúp

```bash
omi --help
omi conversation --help
```

## Tài nguyên

- [Tài liệu](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
