# omi-cli سنڌي شروعاتي رهنمائي (Sindhi Quickstart Guide)

`omi-cli` Omi پليٽ فارم جو باضابطه ڪمانڊ لائين ٽول (CLI) آهي. هن جي ذريعي توهان پنهنجون يادون (Memories)، ڳالهه ٻولهه (Conversations)، ۽ ڪمن جي فهرست (Action Items) سڌو سنئون ٽرمينل مان منظم ڪري سگهو ٿا.

---

## ۱. انسٽاليشن (Installation)

`omi-cli` هلائڻ لاءِ Python 3.10 يا ان کان نئون ورشن گهربل آهي.

### pip ذريعي انسٽال ڪريو:
```bash
pip install omi-cli
```

### انسٽاليشن جي تصديق ڪريو:
```bash
omi --version
```

---

## ۲. اٿينٽيڪيشن (Authentication)

Omi API استعمال ڪرڻ لاءِ لاگ ان ٿيڻ لازمي آهي:

### برائوزر ذريعي لاگ ان (Browser OAuth):
```bash
omi auth login --browser
```

### API ڪنجي (API Key) ذريعي لاگ ان:
[app.omi.me](https://app.omi.me) تي وڃو ۽ "Developer → API Keys" مان ڪنجي ٺاهيو:

```bash
# ڪمانڊ لائين ذريعي سيٽ ڪريو:
omi auth login --api-key omi_dev_...

# يا ماحولياتي ويريئيبل (Environment Variable) طور:
export OMI_API_KEY=omi_dev_...
```

### لاگ ان حيثيت چيڪ ڪريو:
* `omi auth status`: مقامي ڪريڊينشيل، ٽوڪن، ۽ مدي ختم ٿيڻ جو وقت ڏيکاري ٿو (آف لائن ڪم ڪري ٿو).
* `omi auth whoami`: Omi سرور سان رابطو ڪري تصديق ڪري ٿو (انٽرنيٽ گهربل آهي).

```bash
omi auth status
omi auth whoami
```

لاگ آئوٽ ڪرڻ لاءِ:
```bash
omi auth logout
```

---

## ۳. بنيادي استعمال (Basic Usage)

### يادون (Memories)

```bash
# تازيون يادون ڏسو (ڊفالٽ ۲۵)
omi memory list

# وڌيڪ يادون ڏسڻ لاءِ حد مقرر ڪريو
omi memory list --limit 20

# مخصوص ياد آءِ ڊي ذريعي ڏسو
omi memory get <memory-id>

# نئين ياد شامل ڪريو
omi memory create "پروجيڪٽ جي ڊيڊ لائن سومر تائين وڌائي وئي"

# ڪا ياد ختم ڪريو
omi memory delete <memory-id>
```

### ڳالهه ٻولهه (Conversations)

```bash
# تازيون ڳالهيون ڏسو
omi conversation list

# پوري ڳالهه ٻولهه جا تفصيل وٺو
omi conversation get <conversation-id>

# ڳالهه ٻولهه جو مڪمل ٽرانسڪرپٽ ڏسو
omi conversation get <conversation-id> --include-transcript
```

### ڪمن جي فهرست (Action Items)

```bash
# باقي رهيل ڪم ڏسو
omi action-item list --open

# مڪمل ٿيل ڪم ڏسو
omi action-item list --completed

# نئون ڪم شامل ڪريو
omi action-item create "رپورٽ سومر تائين جمع ڪرائڻي آهي"

# ڪم کي مڪمل نشان لڳايو
omi action-item complete <item-id>
```

---

## ۴. ترقي يافته آپشن (Advanced Options)

### JSON آئوٽ پٽ:
اسڪرپٽنگ ۽ آٽوميشن لاءِ `--json` فليگ استعمال ڪريو (سب-ڪمانڊ کان اڳ):
```bash
omi --json memory list
omi --json conversation list --limit 5
omi --json action-item list --open
```

> **ضروري قاعدو:** `--json` فليگ مکيه `omi` ڪمانڊ کان پوءِ ۽ سب-ڪمانڊ کان **اڳ** لڳايو:
> * صحيح: `omi --json memory list`
> * غلط: `omi memory list --json`

### وڌيڪ تفصيل ۽ بنا رنگن جو موڊ (Verbose & No-Color):
HTTP ٽريفڪ لاگ ڏسڻ لاءِ `-v` يا `--verbose` ۽ بنا رنگن جي آئوٽ پٽ لاءِ `--no-color` استعمال ڪريو:
```bash
omi --verbose memory list
omi --no-color memory list
```

### پروفائل مئنيجمينٽ (Profiles):
مختلف کاتن يا ماحولن (Dev/Prod) لاءِ الڳ پروفائل استعمال ڪريو:
```bash
# نئون پروفائل تيار ڪريو ۽ سوئچ ڪريو:
omi config profile use work

# نئين پروفائل تحت لاگ ان ٿيو:
omi auth login --api-key omi_dev_work_key...

# مخصوص پروفائل سان ڪمانڊ هلائڻ:
omi --profile work memory list
```

---

## ۵. مسئلن جو حل (Troubleshooting)

* **اٿينٽيڪيشن خرابي (401 Unauthorized):**
  `omi auth whoami` ذريعي ٽوڪن جي تصديق ڪريو. جيڪڏهن ٽوڪن ختم ٿي چڪو آهي ته ٻيهر `omi auth login` ڪريو.
* **ڪنيڪشن مسئلو:**
  انٽرنيٽ ڪنيڪشن ۽ `api.omi.me` تائين رسائي چيڪ ڪريو.
* **مدد (Help):**
  ڪنهن به ڪمانڊ جي مڪمل رهنمائي لاءِ `--help` لڳايو:
  ```bash
  omi --help
  omi memory --help
  ```
