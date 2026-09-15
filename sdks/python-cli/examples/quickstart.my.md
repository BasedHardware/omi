# omi-cli အမြန်စတင်လမ်းညွှန်

## ထည့်သွင်းခြင်း

```bash
pip install omi-cli
```

## ဝင်ရောက်ခြင်း

```bash
omi auth login
```

သင့်အကောင့်ဖြင့် ဝင်ရောက်ရန် ဘရောက်ဆာ ပွင့်လာပါမည်။

## အခြေခံ ညွှန်ကြားချက်များ

### စကားဝိုင်းများ စာရင်း

```bash
omi conversation list
```

### သီးခြား စကားဝိုင်းတစ်ခု ကြည့်ရန်

```bash
omi conversation get <စကားဝိုင်း_ID>
```

### စကားဝိုင်းများ ရှာဖွေခြင်း

```bash
# omi conversation list (search filters)
omi conversation list "ရှာဖွေရန် စကားလုံး"
```

## အဆင့်မြင့် ရွေးချယ်စရာများ

### ကန့်သတ်ချက်ဖြင့် စစ်ထုတ်ခြင်း

```bash
omi conversation list --limit 10
```

### မှတ်တမ်းများ ပါဝင်စေခြင်း

```bash
omi conversation list --include-transcript
```

### JSON ပုံစံဖြင့် ထုတ်ယူခြင်း

```bash
omi --json conversation list
```

### စာမျက်နှာခွဲခြင်း

```bash
omi conversation list --limit 50 --offset 100
```

## ထွက်ခြင်း

```bash
omi auth logout
```

## အကူအညီ

```bash
omi --help
omi conversation --help
```

## အရင်းအမြစ်များ

- [စာရွက်စာတမ်း](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
