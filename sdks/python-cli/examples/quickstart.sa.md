# omi-cli संस्कृत-मार्गदर्शिका (Sanskrit Quickstart Guide)

`omi-cli` इति Omi-मञ्चस्य अधिकृतम् आज्ञापङ्क्ति-साधनम् (CLI tool) अस्ति। अनेन भवन्तः स्वकीय-स्मृतीनां (Memories), सम्भाषणानां (Conversations), कार्यसूचिकानां (Action Items) च प्रबन्धनं टर्मिनल-माध्यमेन कर्तुं शक्नुवन्ति।

---

## १. प्रतिष्ठापनम् (Installation)

`omi-cli` चालयितुं Python 3.10+ आवश्यकम् अस्ति।

### pip द्वारा प्रतिष्ठापयतु:
```bash
pip install omi-cli
```

### प्रतिष्ठापनस्य पुष्टिं करोतु:
```bash
omi --version
```

---

## २. प्रमाणीकरणम् (Authentication)

Omi API उपयोगार्थं प्रमाणीकरणम् आवश्यकम्:

### जालगवेषक-माध्यमेन प्रवेशः (Browser OAuth):
```bash
omi auth login --browser
```

### API-कुञ्चिकायाः उपयोगेन प्रवेशः (API Key):
[app.omi.me](https://app.omi.me) गत्वा "Developer → API Keys" इत्यस्मात् कुञ्चिकां प्राप्य योजयतु:

```bash
# आज्ञापङ्क्त्या निर्धारयतु:
omi auth login --api-key omi_dev_...

# अथवा पर्यावरण-चरेण (CI/CD कृते उत्तमम्):
export OMI_API_KEY=omi_dev_...
```

### प्रमाणीकरण-स्थिति-परीक्षणम्:
* `omi auth status`: स्थानीय-प्रमाणपत्राणि, टोकनं, कालावधिं च दर्शयति (ऑफलाइन कार्यं करोति)।
* `omi auth whoami`: Omi सर्वरेण सह सम्पर्कं कृत्वा सद्यः स्थितिं निर्धारयति (अन्तर्जालम् आवश्यकम्)।

```bash
omi auth status
omi auth whoami
```

प्रमाणीकरणं निष्कासयितुं (Logout):
```bash
omi auth logout
```

---

## ३. मूलभूत-उपयोगः (Basic Usage)

### स्मृतयः (Memories)
प्रणाल्या शिक्षितान् तथ्यान् संभाषयतु:

```bash
# स्मृतीनां सूचिं पश्यतु:
omi memory list

# नूतनां स्मृतिं रचयतु:
omi memory create "उपयोक्ता डार्क-मोड रोचयति" --category lifestyle

# विशिष्ट-स्मृतेः विवरणं पश्यतु:
omi memory get <MEMORY_ID>
```

### सम्भाषणाणि (Conversations)
यन्त्रेण अथवा अनुप्रयुक्त्या (app) ध्वन्यङ्कितानि सम्भाषणाणि:

```bash
# अन्तिमानि ५ सम्भाषणाणि पश्यतु:
omi conversation list --limit 5

# सम्भाषणस्य सम्पूर्णं लेखं (transcript) पश्यतु:
omi conversation get <CONVERSATION_ID> --include-transcript
```

### कार्यसूचिकाः (Action Items)
सम्भाषणात् निष्कासितानि कर्तव्यानि:

```bash
# केवलम् अपूर्ण-कार्याणि पश्यतु:
omi action-item list --open

# कार्यं सम्पन्नम् इति चिह्नीकरोतु:
omi action-item complete <ACTION_ITEM_ID>
```

### लक्षाणि (Goals)
निर्धारित-लक्षाणां सूचिं पश्यतु:

```bash
omi goal list
```

---

## ४. स्क्रिप्टिङ्ग् तथा JSON निर्गमः (`--json`)

`omi-cli` मूलरूपेण JSON निर्गमं समर्थयति। `jq` अथवा अन्यसाधनैः सह उपयोगार्थं `--json` विकल्पः **उपाज्ञायाः पूर्वम्** प्रदातव्यः:

```bash
# स्मृतीः JSON रूपेण प्राप्य ID तथा विषयं निष्कासयतु:
omi --json memory list | jq '.[] | {id, content, category}'

# सम्भाषणानां शीर्षकाणि पश्यतु:
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# अपूर्ण-कार्याणि पश्यतु:
omi --json action-item list --open | jq '.'
```

> **महत्त्वपूर्ण-नियमः:** `--json` विकल्पः सर्वदा `omi` आज्ञायाः अनन्तरम् उप-आज्ञायाः च **पूर्वम्** लेखनीयः:
> * उचितम्: `omi --json memory list`
> * अनुचितम्: `omi memory list --json`

---

## ५. निर्गमन-सङ्केताः (Exit Codes)

स्वचालने (Automation) दोषाणां ज्ञानाय निर्गमन-सङ्केताः:

| सङ्केतः | वर्गः | विवरणम् |
| :---: | :--- | :--- |
| `0` | Success | आज्ञा सफला जाता |
| `1` | Usage Error | अमान्याः विकल्पाः अथवा अपूर्ण-प्राचलाः |
| `2` | Auth Error | अप्रमाणितः प्रवेशः, अमान्या कुञ्चिका वा |
| `3` | Server Error | सर्वर-दोषः (5xx) अथवा जाल-समस्या |
| `4` | Rate Limited | अनुरोध-सीमा अतिक्रान्ता (429 Too Many Requests) |
| `5` | Not Found | याचितं साधनं न प्राप्तम् (404 Not Found) |

---

## ६. शैल-पर्यावरण-चराणां उदाहरणानि

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

## ७. स्थानीय-डेस्कटॉप-API (Local Desktop API)

यदि Omi Desktop सक्रियम् अस्ति तर्हि स्थानीय-यन्त्रस्य दत्तांशः अन्वेष्टुं शक्यते:

```bash
# स्थानीय-सङ्केतं टोकनं च संयोजयतु:
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# स्थानीय-स्थितिं पश्यतु:
omi --json local status

# पटले (screen) अन्वेषणं करोतु:
omi --json local search-screen "परियोजना" --days 7 --app Safari
```

---

## ८. रूपरेखा-प्रबन्धनम् (Profiles Management)

एकाधिकानां खातानां प्रबन्धनाय `--profile` विकल्पं प्रयुञ्जतु:

```bash
# व्यक्तिगत-रूपरेखायां प्रवेशः:
omi --profile personal auth login

# कार्य-रूपरेखायां प्रवेशः:
omi --profile work auth login

# विशिष्ट-रूपरेखया स्मृतीः पश्यतु:
omi --profile work memory list
```
