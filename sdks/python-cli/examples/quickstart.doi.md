# omi-cli डोगरी शुरूआती मार्गदर्शिका (Dogri Quickstart Guide)

`omi-cli` Omi प्लेटफॉर्म दा आधिकारिक कमांड-लाइन टूल (CLI) ऐ। इसदे राहें तुस अपनी यादां (Memories), गल्लबातां (Conversations), ते कम्म-काजें दी सूची (Action Items) गी सीधे अपने टर्मिनल थमां प्रबंधित करी सकदे ओ।

---

## १. स्थापना (Installation)

`omi-cli` गी चलाउने लेई Python 3.10 जां इसदे शा नवे संस्करण दी लोड़ ऐ।

### pip दे राहें इंस्टॉल करो:
```bash
pip install omi-cli
```

### स्थापना दी पुष्टि करो:
```bash
omi --version
```

---

## २. प्रमाणीकरण (Authentication)

Omi API दा इस्तेमाल करने लेई प्रमाणीकरण जरूरी ऐ:

### ब्राउज़र राहें लॉगिन (Browser OAuth):
```bash
omi auth login --browser
```

### API कुँजी (API Key) दे राहें लॉगिन:
[app.omi.me](https://app.omi.me) पर जाओ ते "Developer → API Keys" थमां अपनी कुंजी बनाओ:

```bash
# कमांड-लाइन पर सेट करो:
omi auth login --api-key omi_dev_...

# जां पर्यावरण चर (Environment Variable) दे राहें (CI/CD लेई उत्तम):
export OMI_API_KEY=omi_dev_...
```

### प्रमाणीकरण दी स्थिति जांचो:
* `omi auth status`: स्थानीय क्रेडेंशियल्स, टोकन, ते समाप्ति समय दस्सदा ऐ (ऑफलाइन कम्म करदा ऐ)।
* `omi auth whoami`: Omi सर्वर कन्ने संपर्क करियै चालू स्थिति दस्सदा ऐ (इंटरनेट जरूरी ऐ)।

```bash
omi auth status
omi auth whoami
```

लॉगआउट करने लेई:
```bash
omi auth logout
```

---

## ३. बुनियादी इस्तेमाल (Basic Usage)

### यादां (Memories)

```bash
# हालिया यादां दी सूची दिक्खो (डिफ़ॉल्ट २५)
omi memory list

# मती सीमा तय करो
omi memory list --limit 20

# खास स्मृति गी आईडी कन्नै दिक्खो
omi memory get <memory-id>

# नवीं स्मृति बनाओ
omi memory create "मीटिंग दे दौरान प्रोजेक्ट दी समय-सीमा तय कीती गेई"

# कोई स्मृति मिटाओ
omi memory delete <memory-id>
```

### गल्लबातां (Conversations)

```bash
# हालिया गल्लबातां दी सूची दिक्खो
omi conversation list

# पूरी गल्लबात दा ब्यौरा लैओ
omi conversation get <conversation-id>

# गल्लबात दा पूरा ट्रांसक्रिप्ट दिक्खो
omi conversation get <conversation-id> --include-transcript
```

### कम्म-काज सूची (Action Items)

```bash
# बाकी बचे दे कम्म दिक्खो
omi action-item list --open

# सिर्फ पूरे होई चुके कम्म दिक्खो
omi action-item list --completed

# नवां कम्म जोड़ो
omi action-item create "प्रोजेक्ट रिपोर्ट सोमवार तकर जमा करानी ऐ"

# कम्म गी पूरा मार्क करो
omi action-item complete <item-id>
```

---

## ४. उन्नत विकल्प (Advanced Options)

### JSON आउटपुट:
स्क्रिप्टिंग ते ऑटोमेशन लेई `--json` फ्लैग दा इस्तेमाल करो (सब-कमांड थमां पैह्ले):
```bash
omi --json memory list
omi --json conversation list --limit 5
omi --json action-item list --open
```

> **महत्वपूर्ण नियम:** `--json` फ्लैग मुख्य `omi` कमांड दे बाद ते सब-कमांड थमां **पैह्ले** रक्खो:
> * सही: `omi --json memory list`
> * गलत: `omi memory list --json`

### वर्बोस ते रंग-हीन मोड (Verbose & No-Color):
HTTP ट्रैफ़िक दिक्खने लेई `-v` जां `--verbose` ते बिना रंगें दे आउटपुट लेई `--no-color` दा इस्तेमाल करो:
```bash
omi --verbose memory list
omi --no-color memory list
```

### प्रोफाइल प्रबंधन (Profiles):
अलग-अलग खातें जां वातावरणें (Dev/Prod) लेई प्रोफाइल बनाओ ते इस्तेमाल करो:
```bash
# नवीं प्रोफाइल बनाओ ते स्विच करो:
omi config profile use work

# नवीं प्रोफाइल कन्ने लॉगिन करो:
omi auth login --api-key omi_dev_work_key...

# खास प्रोफाइल कन्ने कमांड चलाओ:
omi --profile work memory list
```

---

## ५. समस्या समाधान (Troubleshooting)

* **प्रमाणीकरण त्रुटि (401 Unauthorized):**
  `omi auth whoami` चलाइयै टोकन दी वैधता जांचो। जेकर टोकन समाप्त होई गेदा ऐ तां परतियै `omi auth login` करो।
* **कनेक्शन समस्या:**
  जांचो जे इंटरनेट कनेक्शन कम्म करदा ऐ ते `api.omi.me` तकर पहुंच उपलब्ध ऐ।
* **मदद (Help):**
  किसे बी कमांड दी विस्तृत जानकारी लेई `--help` जोड़ो:
  ```bash
  omi --help
  omi memory --help
  ```
