# omi-cli एजेंटों के लिए

> LLM-संचालित हार्नेस के लिए व्यावहारिक गाइड (Claude Code, Cursor, अपने बॉट).

## CLI एजेंट-अनुकूल क्यों है

* **स्थिर JSON अनुबंध.** `--json` stdout पर मान्य JSON दस्तावेज़ भेजता है और *केवल* JSON — कोई प्रगति संदेश या स्पिनर नहीं. त्रुटियां stderr पर `{"error": "...", "detail": "..."}` के रूप में जाती हैं.
* **स्थिर एग्जिट कोड.** `0` ok / `1` उपयोग / `2` auth / `3` सर्वर / `4` rate limited / `5` नहीं मिला. एजेंट प्राकृतिक-भाषा त्रुटियों को पार्स किए बिना इन पर शाखा बना सकते हैं.
* **हेडलेस संदर्भों में कोई इंटरैक्टिव प्रॉम्प्ट नहीं.** विनाशकारी कमांडों को `--yes` (या `-y`) दें; इंटरैक्टिव लॉगिन छोड़ने के लिए `--api-key` दें या `OMI_API_KEY` सेट करें.
* **क्षमाशील पुनःप्रयास व्यवहार.** `429` और `5xx` उभरने से पहले बैकऑफ के साथ पुनःप्रयास किए जाते हैं.

## प्रमाणीकरण (एक बार, मनुष्य द्वारा)

उपयोगकर्ता Omi वेब ऐप से dev API key प्राप्त करता है
(`https://app.omi.me` → Developer → API Keys) और या तो:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; key शेल हिस्ट्री में नहीं
# # या
export OMI_API_KEY=omi_dev_...          # क्षणभंगुर, कंटेनर-अनुकूल
```

## पाँच चीज़ें जो एजेंट सबसे ज्यादा करते हैं

### 1. मेमोरीज़ पढ़ना

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक मेमोरी बनाना

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. कन्वर्सेशन पढ़ना

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुले एक्शन आइटम पढ़ना

```bash
omi action-item list --json --open
```

### 5. एक्शन आइटम को पूर्ण चिह्नित करना

```bash
omi action-item complete --json a1b2c3d4
```

## लोकल Desktop API

जब Omi Desktop अपनी लोकल API उजागर करता है, एजेंट ऑन-डिवाइस स्क्रीन
हिस्ट्री, रिकैप, SQL और टास्क को क्लाउड dev API के बिना क्वेरी कर सकते हैं:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# # या, क्षणिक सत्रों के लिए:
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

टास्क तभी पूरे या हटाएं जब उपयोगकर्ता स्पष्ट रूप से कहे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर
लिखता है और स्क्रिप्ट के लिए stdout पर JSON भी प्रिंट करता है. स्क्रीनशॉट ID
आमतौर पर `local search-screen` या `screenshots` टेबल पर SQL से आता है. यदि
Desktop `screenshot_pending`, `screenshot_file_missing` या `screenshot_chunk_corrupted`
जैसी संरचित विफलता लौटाता है, JSON मोड stderr पर `reason`, `hint` और
`screenshot_id` फ़ील्ड संरक्षित रखता है ताकि एजेंट पुरानी ID का पुनःप्रयास कर सके
या सटीक ब्लॉकर बता सके. सफल आउटपुट को विज़न टूल्स में भेजने से पहले `file PATH`
से मान्य करें.

## कार्यित उदाहरण: Python एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सभी खुले एक्शन आइटम पढ़ें और 30 दिन से पुराने को पूर्ण चिह्नित करें.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## रेट लिमिट संभालना

मेमोरीज़: 120/घंटा. कन्वर्सेशन: 25/घंटा. बैच निर्माण: 15/घंटा.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] ऐसा दिखता है: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## टिप्स

* यदि एजेंट कई Omi अकाउंट संभालता है तो `--profile <name>` उपयोग करें. हर
  प्रोफाइल की अपनी credential और API base होती है.
* लोकल बैकएंड टेस्टिंग के लिए `--api-base http://localhost:8080` उपयोग करें.
* एक रन के लिए प्रोफाइल-लोकल Desktop API सेटिंग ओवरराइड करने हेतु
  `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` उपयोग करें.
* डिबगिंग के लिए `--verbose` उपयोग करें — यह `METHOD path → status (Ns)`
  को stderr पर लॉग करता है, stdout को प्रभावित किए बिना, इसलिए JSON मोड मान्य रहता है.
* कन्वर्सेशन में सामग्री पाइप करने के लिए `--text -` उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
