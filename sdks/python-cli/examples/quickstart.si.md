# omi-cli ඉක්මන් ආරම්භක මාර්ගෝපදේශය

## ස්ථාපනය

```bash
pip install omi-cli
```

## පිවිසීම

```bash
omi auth login
```

ඔබගේ ගිණුම හරහා පිවිසීමට බ්‍රවුසරය විවෘත වේ.

## මූලික විධාන

### සංවාද ලැයිස්තුව

```bash
omi conversation list
```

### විශේෂිත සංවාදයක් බලන්න

```bash
omi conversation get <සංවාද_හැඳුනුම>
```

### සංවාද සෙවීම

```bash
# omi conversation list (search filters)
omi conversation list "සෙවුම් විමසුම"
```

## උසස් විකල්ප

### සීමාව අනුව පෙරීම

```bash
omi conversation list --limit 10
```

### පිටපත් ඇතුළත් කිරීම

```bash
omi conversation list --include-transcript
```

### JSON ආකෘතියෙන් නිර්යාතය

```bash
omi --json conversation list
```

### පිටු කිරීම

```bash
omi conversation list --limit 50 --offset 100
```

## පිටවීම

```bash
omi auth logout
```

## උදව්

```bash
omi --help
omi conversation --help
```

## සම්පත්

- [ලේඛනගත කිරීම](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
