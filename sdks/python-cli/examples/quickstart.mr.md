# omi-cli मराठी क्विकस्टार्ट मार्गदर्शक (Marathi Quickstart Guide)

> टर्मिनलवरून Omi सोबत संवाद साधण्यासाठी व्यावहारिक मार्गदर्शक. व्यक्ती आणि AI एजंट्स दोघांसाठी उपयुक्त.

`omi-cli` हे [Omi](https://omi.me) डेव्हलपर API सोबत संवाद साधण्यासाठी अधिकृत कमांड-लाइन इंटरफेस आहे. हे टूल Omi च्या चार मुख्य संसाधनांवर (मेमरी, संभाषणे, कृती आयटम्स आणि उद्दिष्टे) कार्यक्षमतेने आणि स्क्रिप्टद्वारे प्रक्रिया करण्यास मदत करते.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **अधिकृत दस्तऐवजीकरण:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **सोर्स कोड:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## १. इन्स्टॉलेशन (Installation)

`pipx` वापरून इन्स्टॉल करण्याची शिफारस केली जाते, ज्यामुळे पॅकेजचे अवलंबित्व (dependencies) वेगळे राहते:

```bash
# शिफारस केलेले: pipx वापरून इन्स्टॉलेशन
pipx install omi-cli

# किंवा pip वापरून
pip install omi-cli
```

> **महत्त्वाची टीप: पॅकेजचे नाव आणि कमांडच्या नावातील फरक**
> * Python पॅकेजचे नाव **`omi-cli`** आहे (PyPI वरील स्वतंत्र `omi` हे असंबंधित पॅकेज आहे, ते इन्स्टॉल करू नका).
> * इन्स्टॉलेशननंतर टर्मिनलमध्ये वापरली जाणारी कमांड **`omi`** आहे.

इन्स्टॉलेशननंतर व्हर्जन आणि मदत तपासा:

```bash
omi --version
omi --help
```

---

## २. प्रमाणीकरण (Authentication)

`omi-cli` दोन प्रकारच्या प्रमाणीकरण पद्धतींना सपोर्ट करते:

| पद्धत | मुख्य वापर | उदाहरण कमांड |
| :--- | :--- | :--- |
| **डेव्हलपर API की (`omi_dev_*`)** | CI/CD, ऑटोमेशन स्क्रिप्ट्स, AI एजंट्स | `omi auth login --api-key ...` किंवा पर्यावरण व्हेरिएबल्स |
| **ब्राउझर OAuth (Google/Apple)** | वैयक्तिक कॉम्प्युटर / लॅपटॉप | `omi auth login --browser` |

### परस्परसंवादी लॉगिन (Interactive Login)
पर्यायांशिवाय कमांड चालवल्यास ब्राउझर किंवा API की निवडण्याचा पर्याय मिळतो:

```bash
omi auth login
# 1) Browser — Google किंवा Apple खात्याद्वारे लॉगिन (वापरकर्त्यांसाठी)
# 2) API key — app.omi.me वरून मिळालेली की पेस्ट करा (एजंट्स/CI साठी)
```

### थेट ब्राउझरद्वारे लॉगिन
```bash
omi auth login --browser
```

### API की वापरणे
[app.omi.me](https://app.omi.me) वरील "Developer → API Keys" मधून की मिळवा आणि सेट करा:

```bash
# कमांडद्वारे सेट करा
omi auth login --api-key omi_dev_...

# किंवा पर्यावरण व्हेरिएबलद्वारे (CI/CD साठी सर्वोत्तम)
export OMI_API_KEY=omi_dev_...
```

### प्रमाणीकरण स्थिती तपासणे
* `omi auth status`: स्थानिक क्रेडेंशियल्स, मास्क केलेले टोकन आणि वैधता कालावधी दाखवते (ऑफलाइन कार्य करते).
* `omi auth whoami`: थेट Omi सर्व्हरला विनंती पाठवून क्रेडेंशियल्स सक्रिय असल्याची पडताळणी करते (इंटरनेट आवश्यक).

```bash
omi auth status
omi auth whoami
```

क्रेडेंशियल्स हटवण्यासाठी लॉगआउट करा:
```bash
omi auth logout
```

कॉन्फिगरेशन डीफॉल्टनुसार `~/.omi/config.toml` मध्ये साठवले जाते. ही फाईल कोणासोबतही शेअर करू नका.

---

## ३. मूलभूत वापर (Basic Usage)

Omi च्या चार मुख्य घटकांचे व्यवस्थापन खालीलप्रमाणे करता येते:

### मेमरीज (Memories)
प्रणालीने शिकलेली माहिती आणि तथ्ये व्यवस्थापित करा:

```bash
# मेमरींची यादी पहा
omi memory list

# नवीन मेमरी तयार करा
omi memory create "वापरकर्ता डार्क मोड पसंत करतो" --category lifestyle

# विशिष्ट मेमरीचे तपशील पहा
omi memory get <MEMORY_ID>
```

### संभाषणे (Conversations)
वेअरेबल डिव्हाइस किंवा ॲपवरून रेकॉर्ड केलेले ऑडिओ आणि ट्रान्सक्रिप्ट:

```bash
# अलीकडील ५ संभाषणे पहा
omi conversation list --limit 5

# संभाषणाचे तपशील आणि संपूर्ण ट्रान्सक्रिप्ट पहा
omi conversation get <CONVERSATION_ID> --include-transcript
```

### कृती आयटम्स (Action Items)
संभाषणांतून आपोआप काढलेली कार्ये:

```bash
# फक्त अपूर्ण कृती आयटम्स पहा
omi action-item list --open

# एखादे कार्य पूर्ण झाले म्हणून चिन्हांकित करा
omi action-item complete <ACTION_ITEM_ID>
```

### उद्दिष्टे (Goals)
ट्रॅक केलेली उद्दिष्टे पहा:

```bash
# उद्दिष्टांची यादी पहा
omi goal list
```

---

## ४. स्क्रिप्टिंग आणि JSON आउटपुट (`--json`)

`omi-cli` नेटिव्ह JSON आउटपुटला सपोर्ट करते. `jq` किंवा इतर टूल्ससोबत वापरताना `--json` हा **ग्लोबल पर्याय सब-कमांडच्या आधी** द्यावा लागतो:

```bash
# मेमरीज JSON स्वरूपात मिळवून ID आणि मजकूर काढा
omi --json memory list | jq '.[] | {id, content, category}'

# अलीकडील संभाषणांचे शीर्षक पहा
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# अपूर्ण कृती आयटम्स JSON मध्ये पहा
omi --json action-item list --open | jq '.'
```

> **महत्त्वाचा नियम:** `--json` नेहमी मुख्य कमांडनंतर आणि सब-कमांडच्या **आधी** लिहा:
> * योग्य: `omi --json memory list`
> * चुकीचे: `omi memory list --json`

### फाईलमध्ये सेव्ह करणे आणि पेजिंग (Pagination)

```bash
# पहिले २५ रेकॉर्ड्स फाईलमध्ये सेव्ह करा
omi --json memory list --limit 25 --offset 0 > yaadi-page-1.json

# पुढील २५ रेकॉर्ड्स मिळवा
omi --json memory list --limit 25 --offset 25 > yaadi-page-2.json
```

---

## ५. एक्झिट कोड्स (Exit Codes)

ऑटोमेशन आणि स्क्रिप्ट्समध्ये त्रुटी ओळखण्यासाठी एक्झिट कोड्स खालीलप्रमाणे आहेत:

| कोड | प्रकार | स्पष्टीकरण |
| :---: | :--- | :--- |
| `0` | Success | कमांड यशस्वीरीत्या पूर्ण झाली |
| `1` | Usage Error | चुकीचे फ्लॅग्स किंवा अपूर्ण पॅरामीटर्स |
| `2` | Auth Error | लॉगिन केलेले नाही, अवैध API की किंवा टोकन संपले |
| `3` | Server Error | सर्व्हर त्रुटी (5xx), नेटवर्क समस्या किंवा टाईमआऊट |
| `4` | Rate Limited | विनंती मर्यादा ओलांडली (429 Too Many Requests) |
| `5` | Not Found | विनंती केलेले संसाधन सापडले नाही (404 Not Found) |

---

## ६. शेलनुसार पर्यावरण व्हेरिएबल्सची उदाहरणे

### Bash / Zsh (Linux / macOS)
```bash
# API की सेट करा
export OMI_API_KEY="omi_dev_your_actual_key_here"

# कमांड चालवा
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API की सेट करा
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# PowerShell मध्ये JSON पार्सिंग
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## ७. स्थानिक डेस्कटॉप API सोबत वापर (Local Desktop API)

Omi Desktop ॲप चालू असल्यास, क्लाउडवर न जाता स्थानिक कॉम्प्युटरवरील डेटा थेट शोधता येतो:

```bash
# स्थानिक API URL आणि टोकन कॉन्फिगर करा
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# स्थानिक स्थिती तपासा
omi --json local status

# स्क्रीन इतिहास शोधा
omi --json local search-screen "प्रकल्प योजना" --days 7 --app Safari
```

---

## ८. प्रोफाईल्स व्यवस्थापन (Profiles)

एकाधिक खाती किंवा चाचणी वातावरण सांभाळण्यासाठी `--profile` पर्याय वापरा:

```bash
# वैयक्तिक प्रोफाईलमध्ये लॉगिन करा
omi --profile personal auth login

# कामाच्या प्रोफाईलमध्ये लॉगिन करा
omi --profile work auth login

# विशिष्ट प्रोफाईल वापरून मेमरीज पहा
omi --profile work memory list
```
