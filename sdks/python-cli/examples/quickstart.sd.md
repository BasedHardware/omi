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
# تازيون يادون ڏسو (ڊفالٽ ۱۰)
omi memories list

# وڌيڪ يادون ڏسڻ لاءِ حد مقرر ڪريو
omi memories list --limit 20

# مخصوص ياد آءِ ڊي ذريعي ڏسو
omi memories get <memory-id>

# نئين ياد شامل ڪريو
omi memories create "پروجيڪٽ جي ڊيڊ لائن سومر تائين وڌائي وئي"

# ڪا ياد ختم ڪريو
omi memories delete <memory-id>
```

### ڳالهه ٻولهه (Conversations)

```bash
# تازيون ڳالهيون ڏسو
omi conversations list

# پوري ڳالهه ٻولهه جا تفصيل وٺو
omi conversations get <conversation-id>

# ڳالهه ٻولهه جو مڪمل ٽرانسڪرپٽ ڏسو
omi conversations transcript <conversation-id>
```

### ڪمن جي فهرست (Action Items)

```bash
# باقي رهيل ڪم ڏسو
omi action-items list

# مڪمل ٿيل ڪم ڏسو
omi action-items list --completed

# نئون ڪم شامل ڪريو
omi action-items create "رپورٽ سومر تائين جمع ڪرائڻي آهي"

# ڪم کي مڪمل نشان لڳايو
omi action-items complete <item-id>
```

---

## ۴. ترقي يافته آپشن (Advanced Options)

### JSON آئوٽ پٽ:
اسڪرپٽنگ ۽ آٽوميشن لاءِ `--json` فليگ استعمال ڪريو:
```bash
omi memories list --json
omi conversations list --json
```

### خاموش موڊ (Quiet Mode):
صرف آءِ ڊيز يا گهٽ ۾ گهٽ معلومات لاءِ `-q` يا `--quiet` استعمال ڪريو:
```bash
omi memories list -q
```

### پروفائل مئنيجمينٽ (Profiles):
مختلف کاتن يا ماحولن (Dev/Prod) لاءِ الڳ پروفائل ٺاهيو:
```bash
omi config profile create work
omi config profile use work
omi auth login --api-key omi_dev_work_key...
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
  omi memories --help
  ```
