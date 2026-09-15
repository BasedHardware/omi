# د omi-cli چټک لارښود

## نصبول

```bash
pip install omi-cli
```

## ننوتل

```bash
omi auth login
```

براوزر به خلاص شي ترڅو تاسو د خپل حساب سره ننوځئ.

## اساسي کمانډونه

### د خبرو اترو لیست

```bash
omi conversation list
```

### یوه ځانګړې خبرې اترې وګورئ

```bash
omi conversation get <د_خبرو_اترو_پیژندنه>
```

### د خبرو اترو لټون

```bash
# omi conversation list (search filters)
omi conversation list "د لټون پوښتنه"
```

## پرمختللي اختیارونه

### د حد په اساس فلټر

```bash
omi conversation list --limit 10
```

### د لیکو شاملول

```bash
omi conversation list --include-transcript
```

### په JSON بڼه صادرول

```bash
omi --json conversation list
```

### مخ پر مخ کول

```bash
omi conversation list --limit 50 --offset 100
```

## وتل

```bash
omi auth logout
```

## مرسته

```bash
omi --help
omi conversation --help
```

## سرچینې

- [اسناد](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
