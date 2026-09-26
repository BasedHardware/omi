# एजेंटों के लिए omi-cli

> LLM-संचालित हार्नेस (Claude Code, Cursor, आपके अपने बॉट्स) के लिए व्यावहारिक गाइड।

## CLI एजेंटों के अनुकूल क्यों है

* **स्थिर JSON अनुबंध।** `--json` stdout पर एक वैध JSON दस्तावेज़ उत्सर्जित करता है और
  *केवल* एक JSON दस्तावेज़ — कोई प्रगति संदेश नहीं, कोई स्पिनर नहीं। त्रुटियाँ stderr पर
  `{"error": "...", "detail": "..."}` के रूप में जाती हैं।
* **स्थिर निकास कोड (Exit Codes)।** `0` ठीक / `1` उपयोग त्रुटि / `2` प्रमाणीकरण विफल / `3` सर्वर त्रुटि / `4` दर
  सीमित (rate limited) / `5` नहीं मिला। एजेंट प्राकृतिक भाषा की त्रुटियों को पार्स किए बिना इन कोडों पर शाखाएँ बना सकते हैं।
* **हेडलेस संदर्भों में कोई इंटरैक्टिव संकेत नहीं।** विनाशकारी आदेशों के लिए `--yes` (या `-y`) पास करें;
  इंटरैक्टिव लॉगिन से बचने के लिए `--api-key` पास करें या `OMI_API_KEY` सेट करें।
* **सहनशील पुनर्चक्रण व्यवहार (Retry Behavior)।** त्रुटियाँ `429` और `5xx` सामने आने से पहले
  घातीय बैकऑफ़ के साथ स्वचालित रूप से पुनः प्रयास की जाती हैं।

## प्रमाणीकरण (मानव द्वारा एक बार)

उपयोगकर्ता Omi वेब ऐप (`https://app.omi.me` → Developer → API Keys) से एक डेवलपर API कुंजी प्राप्त करता है और:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास में नहीं रहती
# या
export OMI_API_KEY=omi_dev_...          # क्षणिक, कंटेनर-अनुकूल
```

## एजेंट सबसे अधिक ये पाँच कार्य करते हैं

### 1. यादें पढ़ें

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक याद बनाएँ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. बातचीत पढ़ें

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुले कार्य पढ़ें

```bash
omi action-item list --json --open
```

### 5. किसी कार्य को पूर्ण चिह्नित करें

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API

जब Omi Desktop अपना स्थानीय API प्रदर्शित करता है, तो एजेंट क्लाउड डेवलपर API का उपयोग किए बिना
डिवाइस पर स्क्रीन इतिहास, रीकैप, SQL और कार्यों को क्वेरी कर सकते हैं:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# या क्षणिक सत्रों के लिए:
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

केवल तभी कार्य पूर्ण या हटाएँ जब उपयोगकर्ता स्पष्ट रूप से पूछे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर लिखता है
और स्क्रिप्ट के लिए stdout पर JSON प्रिंट करता है। स्क्रीनशॉट ID आमतौर पर
`local search-screen` या `screenshots` टेबल पर SQL से आता है। यदि Desktop
`screenshot_pending`, `screenshot_file_missing`, या `screenshot_chunk_corrupted` जैसी संरचित
विफलता लौटाता है, तो JSON मोड stderr पर `reason`, `hint`, और `screenshot_id` फ़ील्ड को सुरक्षित रखता है
ताकि एजेंट किसी पुरानी ID का पुनः प्रयास कर सकें या सटीक समस्या की रिपोर्ट कर सकें। विज़न टूल्स को पास करने से
पहले `file PATH` के साथ सफल आउटपुट सत्यापित करें।

## व्यावहारिक उदाहरण: Python एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड में omi CLI को कॉल करता है, गैर-शून्य निकास कोड पर अपवाद उठाता है।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड में stderr पर संरचित त्रुटियाँ प्रिंट करता है:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi {result.returncode} कोड के साथ समाप्त हुआ: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सभी खुले कार्य पढ़ें और 30 दिनों से अधिक पुराने किसी भी कार्य को पूर्ण चिह्नित करें।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमा प्रबंधन (Rate Limits)

यादें: 120/घंटा। बातचीत: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर सीमा पार हो गई
    err = json.loads(result.stderr)
    # err["detail"] ऐसा दिखता है: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## उपयोगी सुझाव

* यदि आपका एजेंट कई Omi खातों को प्रबंधित करता है, तो `--profile <name>` का उपयोग करें। प्रत्येक
  प्रोफ़ाइल का अपना क्रेडेंशियल और API बेस होता है।
* स्थानीय बैकएंड परीक्षण के लिए `--api-base http://localhost:8080` का उपयोग करें।
* एकल रन के लिए प्रोफ़ाइल-स्थानीय डेस्कटॉप API सेटिंग्स को ओवरराइड करने के लिए
  `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` का उपयोग करें।
* डिबगिंग के लिए `--verbose` का उपयोग करें — यह stdout को प्रभावित किए बिना stderr पर
  `METHOD path → status (Ns)` लॉग करता है, जिससे JSON मोड वैध रहता है।
* बातचीत में सामग्री को पाइप करने के लिए, `--text -` का उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
