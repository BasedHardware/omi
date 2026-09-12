# omi-cli त्वरित प्रारंभ गाइड (हिन्दी)

> टर्मिनल से Omi के साथ इंटरैक्ट करने के लिए व्यावहारिक गाइड। मनुष्यों और AI एजेंटों दोनों के लिए उपयुक्त।

`omi-cli` [Omi](https://omi.me) के डेवलपर API के साथ इंटरैक्ट करने के लिए आधिकारिक कमांड-लाइन इंटरफ़ेस है। यह Omi के चार मुख्य संसाधनों — **मेमोरी, बातचीत, एक्शन आइटम और लक्ष्यों** — को कुशलतापूर्वक और स्क्रिप्टेबल तरीके से संभालता है।

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **आधिकारिक दस्तावेज़:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **सोर्स कोड:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. इंस्टॉलेशन

अनुशंसित इंस्टॉलेशन विधि निर्भरताओं को अलग करने के लिए `pipx` का उपयोग करना है।

```bash
# अनुशंसित: pipx के साथ इंस्टॉल करें
pipx install omi-cli

# वैकल्पिक रूप से: pip का उपयोग करें
pip install omi-cli
```

> **महत्वपूर्ण: पैकेज नाम और कमांड नाम के बीच का अंतर**
> * इंस्टॉल किया गया Python पैकेज **`omi-cli`** नाम से है (स्टैंडअलोन `omi` पैकेज एक अलग, असंबंधित पैकेज है)।
> * इंस्टॉलेशन के बाद टर्मिनल में निष्पादन योग्य कमांड का नाम **`omi`** है।

इंस्टॉलेशन के बाद संस्करण और सहायता की जाँच करें।

```bash
omi --version
omi --help
```

---

## 2. प्रमाणीकरण (Authentication)

`omi-cli` दो प्रमाणीकरण विधियों का समर्थन करता है।

| विधि | अनुशंसित उपयोग | उदाहरण कमांड |
| :--- | :--- | :--- |
| **डेवलपर API कुंजी (`omi_dev_*`)** | CI/CD, स्वचालित स्क्रिप्ट, AI एजेंट | `omi auth login --api-key ...` या पर्यावरण चर |
| **ब्राउज़र OAuth (Google/Apple)** | डेवलपर PC / लैपटॉप | `omi auth login --browser` |

### इंटरैक्टिव लॉगिन
विकल्पों के बिना, आपको ब्राउज़र लॉगिन और API कुंजी इनपुट के बीच चयन करने के लिए कहा जाएगा।

```bash
omi auth login
# 1) ब्राउज़र — अपने Google या Apple खाते से लॉग इन करें (मनुष्यों के लिए)
# 2) API कुंजी — app.omi.me से डेवलपर कुंजी पेस्ट करें (एजेंटों/CI के लिए)
```

### सीधे ब्राउज़र के माध्यम से लॉगिन
```bash
omi auth login --browser
```

### API कुंजी का उपयोग
[app.omi.me](https://app.omi.me) पर **Developer → API Keys** से डेवलपर कुंजी प्राप्त करें, फिर इसे सेट करें।

```bash
# कमांड के माध्यम से सेट करें
omi auth login --api-key omi_dev_...

# या पर्यावरण चर के माध्यम से (CI/CD या कंटेनरों के लिए आदर्श)
export OMI_API_KEY=omi_dev_...
```

### प्रमाणीकरण स्थिति की जाँच
* `omi auth status`: स्थानीय प्रोफ़ाइल, मास्क किया गया टोकन और समाप्ति तिथि दिखाता है (ऑफ़लाइन काम करता है)।
* `omi auth whoami`: Omi सर्वर को वास्तविक प्रमाणीकरण अनुरोध भेजता है (नेटवर्क कनेक्शन आवश्यक)।

```bash
omi auth status
omi auth whoami
```

लॉग आउट करने के लिए:
```bash
omi auth logout
```

---

## 3. मूल उपयोग

आप Omi के चार मुख्य संसाधनों को सूचीबद्ध और प्रबंधित कर सकते हैं।

### मेमोरी (Memories)
सिस्टम द्वारा सीखे गए तथ्यों और ज्ञान को प्रबंधित करें।

```bash
# सभी मेमोरी सूचीबद्ध करें
omi memory list

# नई मेमोरी बनाएं
omi memory create "उपयोगकर्ता डार्क मोड पसंद करता है" --category lifestyle

# किसी विशिष्ट मेमोरी का विवरण दिखाएं
omi memory get <MEMORY_ID>
```

### बातचीत (Conversations)
पहनने योग्य डिवाइस या ऐप द्वारा कैप्चर की गई बातचीत का ऑडियो या टेक्स्ट इतिहास।

```bash
# अंतिम 5 बातचीत प्राप्त करें
omi conversation list --limit 5

# बातचीत का विवरण और ट्रांसक्रिप्ट दिखाएं
omi conversation get <CONVERSATION_ID> --include-transcript
```

### एक्शन आइटम (Action Items)
बातचीत से स्वचालित रूप से निकाले गए कार्य या फ़ॉलो-अप आइटम।

```bash
# केवल खुले एक्शन आइटम सूचीबद्ध करें
omi action-item list --open

# एक्शन आइटम को पूर्ण के रूप में चिह्नित करें
omi action-item complete <ACTION_ITEM_ID>
```

### लक्ष्य (Goals)
उन लक्ष्यों को प्रबंधित करें जिनकी प्रगति को ट्रैक किया जाता है।

```bash
# सभी लक्ष्य सूचीबद्ध करें
omi goal list
```

---

## 4. स्क्रिप्ट प्रसंस्करण और JSON आउटपुट (`--json`)

`omi-cli` मूल रूप से JSON आउटपुट का समर्थन करता है। `jq` या Python स्क्रिप्ट के साथ संयोजन में, **वैश्विक विकल्प** `--json` को उप-कमांड से पहले रखा जाना चाहिए।

```bash
# JSON में मेमोरी सूची प्राप्त करें और ID और सामग्री निकालें
omi --json memory list | jq '.[] | {id, content, category}'

# अंतिम 5 बातचीत के शीर्षक प्राप्त करें
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# खुले एक्शन आइटम सूचीबद्ध करें
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# लक्ष्य सूचीबद्ध करें
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. सत्र निदान

त्वरित समस्या निवारण के लिए इन दो कमांडों को जोड़े में उपयोग करें।

```bash
# 1) पहले स्थानीय कॉन्फ़िगरेशन की जाँच करें
omi auth status

# 2) Omi सर्वर के साथ पुष्टि करें
omi auth whoami

# 3) यदि आवश्यक हो, तो लॉगिन पुनः प्रारंभ करें
omi auth login
```

---

## 6. सर्वोत्तम प्रथाएँ

* **स्क्रिप्ट में `--json` का उपयोग करें:** मुक्त पाठ को पार्स करने से बचें; हमेशा संरचित JSON आउटपुट पर भरोसा करें।
* **`pipx` के साथ वातावरण को अलग करें:** अन्य Python पैकेजों के साथ निर्भरता संघर्ष से बचता है।
* **API कुंजी साझा न करें:** `omi_dev_*` कुंजियाँ पूर्ण खाता पहुँच प्रदान करती हैं — उन्हें एक सीक्रेट मैनेजर या पर्यावरण चर में संग्रहीत करें।
* **साझा डिवाइस से लॉग आउट करें:** साझा मशीनों पर सत्र के बाद `omi auth logout` का उपयोग करें।

---

## 7. समस्या निवारण

| लक्षण | संभावित कारण | समाधान |
| :--- | :--- | :--- |
| `command not found: omi` | PATH में pipx bin निर्देशिका नहीं है | `pipx ensurepath` चलाएं और टर्मिनल पुनः प्रारंभ करें |
| `401 Unauthorized` | API कुंजी अमान्य या समाप्त हो गई | app.omi.me पर नई कुंजी बनाएं और अपडेट करें |
| `connection refused` | Omi सर्वर तक कोई नेटवर्क पहुँच नहीं | इंटरनेट कनेक्शन और प्रॉक्सी सेटिंग्स की जाँच करें |
| कॉन्फ़िगरेशन फ़ाइलों पर `permission denied` | कॉन्फ़िगरेशन निर्देशिका लिखने योग्य नहीं है | `~/.omi/config.toml` की अनुमतियों की जाँच करें |

---

## 8. त्वरित लिंक

* सोर्स रिपॉजिटरी: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* पूर्ण दस्तावेज़: [docs.omi.me](https://docs.omi.me)
* मुद्दे और समर्थन: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Discord समुदाय: Omi होमपेज के माध्यम से आमंत्रण उपलब्ध