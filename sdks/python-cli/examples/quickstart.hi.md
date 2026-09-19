# omi-cli हिंदी मार्गदर्शिका (Hindi Quickstart Guide)

`omi-cli` Omi प्लेटफॉर्म का आधिकारिक कमांड-लाइन इंटरफ़ेस (CLI) टूल है। इसके माध्यम से आप अपने टर्मिनल से ही अपनी यादों (Memories), वार्तालापों (Conversations) और कार्य सूचियों (Action Items) का प्रबंधन कर सकते हैं।

---

## १. इंस्टालेशन (Installation)

`omi-cli` को चलाने के लिए Python 3.10 या उससे नया संस्करण आवश्यक है।

### pip द्वारा इंस्टॉल करें:
```bash
pip install omi-cli
```

### इंस्टालेशन की पुष्टि करें:
```bash
omi --version
```

---

## २. प्रमाणीकरण (Authentication)

Omi API का उपयोग करने के लिए प्रमाणीकरण आवश्यक है:

### वेब ब्राउज़र द्वारा लॉगिन (Browser OAuth):
```bash
omi auth login --browser
```

### API Key द्वारा लॉगिन (API Key):
[app.omi.me](https://app.omi.me) पर जाकर "Developer → API Keys" से अपनी कुंजी प्राप्त करें और जोड़ें:

```bash
# सीधे कमांड-लाइन से कुंजी सेट करें:
omi auth login --api-key omi_dev_...

# या पर्यावरण चर (Environment Variable) द्वारा सेट करें:
export OMI_API_KEY=omi_dev_...
```

### प्रमाणीकरण स्थिति जांचें:
* `omi auth status`: स्थानीय क्रेडेंशियल्स, टोकन और समाप्ति समय दिखाता है (ऑफ़लाइन काम करता है)।
* `omi auth whoami`: Omi सर्वर से कनेक्ट होकर वर्तमान खाता विवरण सत्यापित करता है (इंटरनेट आवश्यक)।

```bash
omi auth status
omi auth whoami
```

लॉगआउट करने के लिए:
```bash
omi auth logout
```

---

## ३. बुनियादी उपयोग (Basic Usage)

### यादें (Memories)
सिस्टम द्वारा संचित तथ्यों और ज्ञान को देखें:

```bash
# यादों की सूची देखें:
omi memory list

# नई याद जोड़ें:
omi memory create "उपयोगकर्ता डार्क मोड पसंद करता है" --category lifestyle

# विशिष्ट याद का विवरण देखें:
omi memory get <MEMORY_ID>
```

### वार्तालाप (Conversations)
आपके डिवाइस या ऐप द्वारा रिकॉर्ड किए गए वार्तालाप:

```bash
# अंतिम ५ वार्तालाप देखें:
omi conversation list --limit 5

# पूरे ट्रांसक्रिप्ट (Transcript) के साथ वार्तालाप देखें:
omi conversation get <CONVERSATION_ID> --include-transcript
```

### कार्य सूचियां (Action Items)
वार्तालापों से निकाले गए कार्य:

```bash
# केवल लंबित (Open) कार्यों को देखें:
omi action-item list --open

# किसी कार्य को पूर्ण चिह्नित करें:
omi action-item complete <ACTION_ITEM_ID>
```

### लक्ष्य (Goals)
सक्रिय लक्ष्यों की सूची देखें:

```bash
omi goal list
```

---

## ४. स्क्रिप्टिंग और JSON आउटपुट (`--json`)

`omi-cli` नेटिव JSON आउटपुट का समर्थन करता है। `jq` या अन्य टूल्स के साथ उपयोग करने के लिए `--json` फ़्लैग को **सब-कमांड से पहले** लगाएं:

```bash
# यादों को JSON रूप में प्राप्त करें और केवल ID व कंटेंट निकालें:
omi --json memory list | jq '.[] | {id, content, category}'

# वार्तालापों के शीर्षक देखें:
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# खुले कार्यों की सूची JSON में देखें:
omi --json action-item list --open | jq '.'
```

> **महत्वपूर्ण नियम:** `--json` फ़्लैग हमेशा `omi` के तुरंत बाद और सब-कमांड से **पहले** आना चाहिए:
> * सही: `omi --json memory list`
> * गलत: `omi memory list --json`

---

## ५. एक्ज़िट कोड्स (Exit Codes)

स्वचालन (Automation) और स्क्रिप्ट में त्रुटि जांच के लिए एक्ज़िट कोड्स:

| कोड | प्रकार | विवरण |
| :---: | :--- | :--- |
| `0` | Success | कमांड सफलतापूर्वक पूर्ण हुई |
| `1` | Usage Error | अमान्य विकल्प या अधूरा इनपुट |
| `2` | Auth Error | अप्रमाणित सत्र या अमान्य API कुंजी |
| `3` | Server Error | Omi सर्वर त्रुटि (5xx) या नेटवर्क विफलता |
| `4` | Rate Limited | अनुरोध सीमा समाप्त (429 Too Many Requests) |
| `5` | Not Found | अनुरोधित संसाधन नहीं मिला (404 Not Found) |

---

## ६. शैल पर्यावरण उदाहरण (Environment Variables)

### Linux / macOS (Bash & Zsh)
```bash
export OMI_API_KEY="omi_dev_your_actual_key_here"
omi --json memory list --limit 10
```

### Windows (PowerShell)
```powershell
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## ७. स्थानीय डेस्कटॉप API (Local Desktop API)

यदि Omi Desktop ऐप चल रहा है, तो आप स्थानीय डेटा भी एक्सेस कर सकते हैं:

```bash
# स्थानीय एंडपॉइंट और टोकन कॉन्फ़िगर करें:
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# स्थानीय स्थिति जांचें:
omi --json local status

# स्क्रीन मेमोरी में खोजें:
omi --json local search-screen "प्रोजेक्ट रिपोर्ट" --days 7 --app Chrome
```

---

## ८. प्रोफ़ाइल प्रबंधन (Profiles Management)

एकाधिक खातों के बीच आसानी से स्विच करने के लिए `--profile` फ़्लैग का उपयोग करें:

```bash
# व्यक्तिगत प्रोफ़ाइल में लॉगिन करें:
omi --profile personal auth login

# कार्य (Work) प्रोफ़ाइल में लॉगिन करें:
omi --profile work auth login

# विशिष्ट प्रोफ़ाइल के तहत डेटा देखें:
omi --profile work memory list
```
