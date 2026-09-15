# دليل البدء السريع لواجهة سطر الأوامر omi-cli

## التثبيت

```bash
pip install omi-cli
```

## تسجيل الدخول

```bash
omi auth login
```

سيتم فتح المتصفح لتسجيل الدخول عبر حسابك.

## الأوامر الأساسية

### عرض المحادثات

```bash
omi conversation list
```

### عرض محادثة محددة

```bash
omi conversation get <معرف_المحادثة>
```

### البحث في المحادثات

```bash
omi conversation search "استعلام البحث"
```

## خيارات متقدمة

### تصفية حسب الحد الأقصى

```bash
omi conversation list --limit 10
```

### تضمين النصوص الكاملة

```bash
omi conversation list --include-transcript
```

### التصدير بصيغة JSON

```bash
omi conversation list --json
```

### التقسيم إلى صفحات

```bash
omi conversation list --limit 50 --offset 100
```

## تسجيل الخروج

```bash
omi auth logout
```

## المساعدة

```bash
omi --help
omi conversation --help
```

## الموارد

- [التوثيق](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
