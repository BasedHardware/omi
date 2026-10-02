# omi-cli कोंकणी मार्गदर्शक (Konkani Quickstart Guide)

`omi-cli` हें Omi प्लॅटफॉर्म खातीर एक अधिकृत कमांड-लाइन साधन (CLI tool) आसा. हाच्या आदारान तुमी तुमच्या मेमरीज (Memories), संभाशणां (Conversations), कृती आयटम्स (Action Items) आनी हेर गजालींचे व्यवस्थापन टर्मिनल वरवीं करूंक शकतात.

---

## १. प्रतिष्ठापना (Installation)

`omi-cli` प्रतिष्ठापीत करपाक Python 3.10+ आवश्यक आसा.

### pip वरवीं प्रतिष्ठापीत करात:
```bash
pip install omi-cli
```

### प्रतिष्ठापनेची खात्री करात:
```bash
omi --version
```

---

## २. प्रमाणीकरण (Authentication)

Omi API वापरपा खातीर प्रमाणीकरण करचें पडटा:

### ब्राऊझर वरवीं लॉगिन (शिफारस केल्लें):
```bash
omi auth login --browser
```

### API की (API Key) वापरून लॉगिन:
[app.omi.me](https://app.omi.me) चेर वचून "Developer → API Keys" विभागांतल्यान तुमची API की काडात आनी सेट करात:

```bash
# कमांड वरवीं सेट करात:
omi auth login --api-key omi_dev_...

# किंवा पर्यावरण व्हेरिएबल (Environment Variable) वरवीं:
export OMI_API_KEY=omi_dev_...
```

### प्रमाणीकरण स्थिती तपासप:
* `omi auth status`: थळाव्या संगणकाचेर साठयिल्ल्यो क्रेडेंशियल्स, टोकन आनी वैधताय दाखयता (ऑफलाइन कार्य करता).
* `omi auth whoami`: थेट Omi सर्व्हराक विनंती धाडून क्रेडेंशियल्स चालू आसात काय ना तें तपासता (इंटरनेट जाय).

```bash
omi auth status
omi auth whoami
```

लॉगआउट करपाक:
```bash
omi auth logout
```

---

## ३. मूलभूत वापर (Basic Usage)

### मेमरीज (Memories)
प्रणालींत जतनाय केल्ली म्हायती आनी तथ्य सांभाळात:

```bash
# मेमरींची वळेरी पळयात:
omi memory list

# नवी मेमरी तयार करात:
omi memory create "वापरपी डार्क मोड पसंत करता" --category lifestyle

# खाशेल्या मेमरीचो तपशील पळयात:
omi memory get <MEMORY_ID>
```

### संभाशणां (Conversations)
वेअरेबल डिव्हायस किंवा ॲपांतल्यान नोंद केल्लीं संभाशणां:

```bash
# निमाणीं ५ संभाशणां पळयात:
omi conversation list --limit 5

# संभाशणाचो तपशील आनी संपूर्ण ट्रान्सक्रिप्ट पळयात:
omi conversation get <CONVERSATION_ID> --include-transcript
```

### कृती आयटम्स (Action Items)
संभाशणांतल्यान आपशीं तयार जाल्लीं कामां:

```bash
# फकत अपूर्ण आशिल्लीं कामां पळयात:
omi action-item list --open

# खंयचेंय काम पूर्ण जालें म्हूण खूण करात:
omi action-item complete <ACTION_ITEM_ID>
```

### उद्दिश्टां (Goals)
ट्रॅक केल्लीं उद्दिश्टां पळयात:

```bash
# उद्दिश्टांची वळेरी पळयात:
omi goal list
```

---

## ४. स्क्रिप्टिंग आनी JSON आउटपुट (`--json`)

`omi-cli` नेटिव्ह JSON आउटपुटाक तेंको दिता. `jq` किंवा हेर साधनां वांगडा वापरताना `--json` पर्याय **सब-कमांडच्या पयलीं** दिवचो पडटा:

```bash
# मेमरीज JSON स्वरूपांत मेळोवन ID आनी मजकूर काडात:
omi --json memory list | jq '.[] | {id, content, category}'

# निमाण्या संभाशणांचीं नांवां पळयात:
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# अपूर्ण कृती आयटम्स JSON स्वरूपांत पळयात:
omi --json action-item list --open | jq '.'
```

> **महत्वाचो नेम:** `--json` हो पर्याय ओमीच्या मुखेल कमांड उपरांत आनी सब-कमांडच्या **पयलीं** बरोवचो:
> * योग्य: `omi --json memory list`
> * चुकीचें: `omi memory list --json`

---

## ५. एक्झिट कोड्स (Exit Codes)

ऑटोमेशन आनी स्क्रिप्ट्स खातीर एक्झिट कोड्स:

| कोड | प्रकार | विवरण |
| :---: | :--- | :--- |
| `0` | Success | कमांड यशस्वीपणान पूर्ण जाली |
| `1` | Usage Error | चुकीचे फ्लॅग्स किंवा अपूर्ण पॅरामीटर्स |
| `2` | Auth Error | लॉगिन ना, अवैध API की किंवा टोकन सोंपलां |
| `3` | Server Error | सर्व्हर त्रुटी (5xx), नेटवर्क अडचण किंवा टाईमआऊट |
| `4` | Rate Limited | विनंती मर्यादा सोंपली (429 Too Many Requests) |
| `5` | Not Found | सोदिल्लें साधन मेळ्ळें ना (404 Not Found) |

---

## ६. शेल पर्यावरण व्हेरिएबल्सचीं उदाहरणां

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_your_actual_key_here"
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## ७. थळावो डेस्कटॉप API (Local Desktop API)

Omi Desktop ॲप चालू आसल्यार क्लाउडाचेर वचनासतना थेट थळाव्या कॉम्प्युटरा वयलो डेटा सोदूंक मेळटा:

```bash
# थळावो API URL आनी टोकन सेट करात:
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# थळावी स्थिती तपासात:
omi --json local status

# स्क्रीन इतिहास सोदात:
omi --json local search-screen "प्रकल्प योजना" --days 7 --app Safari
```

---

## ८. प्रोफाईल्स व्यवस्थापन (Profiles Management)

एकापरस चड खातीं सांभाळपाक `--profile` पर्याय वापरात:

```bash
# वैयक्तिक प्रोफाईल:
omi --profile personal auth login

# कामाचें प्रोफाईल:
omi --profile work auth login

# खाशेल्या प्रोफाईलांतल्यो मेमरीज पळयात:
omi --profile work memory list
```
