# የomi-cli ፈጣን ጅምር መመሪያ

## መጫን

```bash
pip install omi-cli
```

## መግባት

```bash
omi auth login
```

በመለያዎ ለመግባት አሳሽ ይከፈታል።

## መሰረታዊ ትዕዛዞች

### ውይይቶችን ዘርዝር

```bash
omi conversation list
```

### የተወሰነ ውይይት ይመልከቱ

```bash
omi conversation get <የውይይት_መለያ>
```

### ውይይቶችን ፈልግ

```bash
# omi conversation list (search filters)
omi conversation list "የፍለጋ ጥያቄ"
```

## ከፍተኛ አማራጮች

### በገደብ ማጣራት

```bash
omi conversation list --limit 10
```

### ግልባጮችን ማካተት

```bash
omi conversation list --include-transcript
```

### በJSON ቅርጸት ማውጣት

```bash
omi --json conversation list
```

### ገጽ በገጽ ማሳየት

```bash
omi conversation list --limit 50 --offset 100
```

## መውጣት

```bash
omi auth logout
```

## እገዛ

```bash
omi --help
omi conversation --help
```

## ምንጮች

- [ሰነድ](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
