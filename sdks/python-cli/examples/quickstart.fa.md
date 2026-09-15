# راهنمای شروع سریع omi-cli

## نصب

```bash
pip install omi-cli
```

## ورود

```bash
omi auth login
```

مرورگر باز می‌شود تا با حساب کاربری خود وارد شوید.

## دستورات پایه

### لیست مکالمات

```bash
omi conversation list
```

### مشاهده یک مکالمه خاص

```bash
omi conversation get <شناسه_مکالمه>
```

### جستجوی مکالمات

```bash
# omi conversation list (search filters)
omi conversation list "عبارت جستجو"
```

## گزینه‌های پیشرفته

### فیلتر بر اساس محدودیت

```bash
omi conversation list --limit 10
```

### شامل رونوشت‌ها

```bash
omi conversation list --include-transcript
```

### خروجی به فرمت JSON

```bash
omi --json conversation list
```

### صفحه‌بندی

```bash
omi conversation list --limit 50 --offset 100
```

## خروج

```bash
omi auth logout
```

## راهنما

```bash
omi --help
omi conversation --help
```

## منابع

- [مستندات](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
