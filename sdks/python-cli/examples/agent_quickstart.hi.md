# AI एजेंट्स के लिए omi-cli गाइड

> एलएलएम-आधारित वातावरण (Claude Code, Cursor, कस्टम बॉट्स) के लिए व्यावहारिक मार्गदर्शिका।

## CLI एजेंट्स के लिए अनुकूल क्यों है

* **स्थिर JSON अनुबंध:** `--json` फ्लैग मानक आउटपुट (stdout) पर केवल वैध JSON दस्तावेज़ उत्सर्जित करता है — कोई स्थिति लॉग या स्पिनर नहीं। त्रुटियाँ stderr पर `{"error": "...", "detail": "..."}` के रूप में आती हैं।
* **स्थिर निकास कोड:** `0` ठीक / `1` उपयोग त्रुटि / `2` प्रमाणीकरण त्रुटि / `3` सर्वर त्रुटि / `4` दर सीमा पार / `5` नहीं मिला। एजेंट्स बिना किसी जटिल पार्सिंग के सीधे निकास कोड के आधार पर लॉजिक ब्रांच कर सकते हैं।
* **हेडलेस मोड में कोई इंटरैक्टिव प्रॉम्प्ट नहीं:** विनाशकारी कमांड्स के लिए `--yes` (या `-y`) पास करें; इंटरैक्टिव ब्राउज़र लॉगिन छोड़ने के लिए `--api-key` पास करें या `OMI_API_KEY` सेट करें।
* **स्वचालित पुनः प्रयास:** विफल होने से पहले `429` और `5xx` प्रतिक्रियाओं को एक्सपोनेंशियल बैकऑफ़ के साथ स्वचालित रूप से पुनः आज़माया जाता है।

## प्रमाणीकरण (मानव द्वारा एक बार)

उपयोगकर्ता Omi वेब ऐप (`https://app.omi.me` → Developer → API Keys) से डेवलपर API कुंजी प्राप्त करता है और चलाता है:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास में नहीं जाती
# या
export OMI_API_KEY=omi_dev_...          # अस्थायी, कंटेनरों और CI/CD के लिए आदर्श
```

## एजेंट्स द्वारा किए जाने वाले 5 सबसे सामान्य कार्य

### 1. यादें (Memories) पढ़ना

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक याद बनाना

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. बातचीत (Conversations) पढ़ना

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुले कार्य (Action Items) पढ़ना

```bash
omi action-item list --json --open
```

### 5. किसी कार्य को पूर्ण चिह्नित करना

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API (Local Desktop API)

जब Omi Desktop अपना स्थानीय API सक्षम करता है, तो एजेंट्स क्लाउड API का उपयोग किए बिना डिवाइस स्क्रीन इतिहास, सारांश, SQL और कार्यों को क्वेरी कर सकते हैं:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# या अस्थायी सत्रों के लिए:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

कार्यों को केवल तभी पूरा या हटाएँ जब उपयोगकर्ता स्पष्ट रूप से अनुरोध करे:

```bash
omi --json local task complete task_1
```
