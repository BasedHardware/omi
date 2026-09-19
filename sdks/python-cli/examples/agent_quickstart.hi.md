# एजेंट्स के लिए omi-cli

> LLM-संचालित वातावरण (Claude Code, Cursor, आपके खुद के बॉट्स) के लिए व्यावहारिक गाइड।

## CLI एजेंट-अनुकूल क्यों है

* **स्थिर JSON अनुबंध.** `--json` stdout पर एक वैध JSON दस्तावेज़ आउटपुट करता है और *केवल* वही — कोई प्रगति संदेश या स्पिनर नहीं। त्रुटियाँ stderr पर `{"error": "...", "detail": "..."}` के रूप में लिखी जाती हैं।
* **स्थिर निकास कोड.** `0` ठीक / `1` उपयोग त्रुटि / `2` अनुमति त्रुटि / `3` सर्वर त्रुटि / `4` दर सीमा / `5` नहीं मिला। एजेंट इन कोडों पर बिना त्रुटि संदेशों में प्राकृतिक भाषा पार्स किए शाखा ले सकते हैं।
* **हेडलेस संदर्भों में कोई इंटरैक्टिव प्रॉम्प्ट नहीं.** विनाशकारी कमांड के लिए `--yes` (या `-y`) पास करें; इंटरैक्टिव लॉगिन को छोड़ने के लिए `--api-key` पास करें या `OMI_API_KEY` सेट करें।
* **क्षमाशील रिट्री लॉजिक.** रिपोर्ट करने से पहले `429` और `5xx` को एक्सपोनेंशियल बैकऑफ के साथ रिट्राई किया जाता है।

## प्रमाणीकरण (एक बार, मानव द्वारा)

उपयोगकर्ता Omi वेब ऐप से डेवलपर API कुंजी प्राप्त करता है (`https://app.omi.me` → Developer → API Keys) और या तो चलाता है:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास में नहीं जाती
# oder / ou / ili / or / ή / veya / või / o / ale /
export OMI_API_KEY=omi_dev_...          # अस्थायी, कंटेनर-अनुकूल
```

## पाँच चीजें जो एजेंट सबसे ज्यादा करते हैं

### 1. यादें पढ़ें

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक याद बनाएं

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. बातचीत पढ़ें

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुले एक्शन आइटम पढ़ें

```bash
omi action-item list --json --open
```

### 5. एक एक्शन आइटम को पूर्ण करें

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय Desktop API

जब Omi Desktop अपना स्थानीय API उजागर करता है, तो एजेंट क्लाउड dev API का उपयोग किए बिना ऑन-डिवाइस स्क्रीन इतिहास, सारांश, SQL और कार्यों को क्वेरी कर सकते हैं:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# अस्थायी, कंटेनर-अनुकूल:
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

कार्यों को केवल तभी पूर्ण करें या हटाएं जब उपयोगकर्ता स्पष्ट रूप से माँगे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर सहेजता है और स्क्रिप्ट के लिए stdout पर JSON भी लिखता है। स्क्रीनशॉट ID आमतौर पर `local search-screen` या `screenshots` तालिका पर SQL से आती है। यदि Desktop `screenshot_pending`, `screenshot_file_missing` या `screenshot_chunk_corrupted` जैसी संरचित त्रुटि लौटाता है, तो JSON मोड stderr पर `reason`, `hint` और `screenshot_id` फ़ील्ड को संरक्षित करता है ताकि एजेंट पुराने ID के साथ पुनः प्रयास कर सकें या सटीक बाधा की रिपोर्ट कर सकें। विज़न टूल्स को पास करने से पहले `file PATH` से सफल परिणामों की जाँच करें।

## व्यावहारिक उदाहरण: Python एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड में omi CLI चलाएं और खराब निकास कोडों पर अपवाद फेंकें।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड में stderr को संरचित त्रुटियाँ लिखता है:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi से बाहर निकला {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सभी खुले एक्शन आइटम पढ़ें और 30 दिनों से पुराने को पूर्ण चिह्नित करें।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमा प्रबंधन

यादें: 120/घंटा। बातचीत: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर सीमा पार हो गई
    err = json.loads(result.stderr)
    # err["detail"] ऐसा दिखता है: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## सुझाव

* यदि आपका एजेंट कई Omi खाते प्रबंधित करता है तो `--profile <नाम>` का उपयोग करें। प्रत्येक प्रोफ़ाइल की अपनी क्रेडेंशियल और API बेस होती है।
* स्थानीय बैकएंड परीक्षण के लिए `--api-base http://localhost:8080` का उपयोग करें।
* एकल रन के लिए प्रोफ़ाइल की Desktop API सेटिंग्स को ओवरराइड करने के लिए `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` का उपयोग करें।
* डीबगिंग के लिए `--verbose` का उपयोग करें — यह stderr पर `METHOD path → status (Ns)` लॉग करता है बिना stdout को प्रभावित किए, इसलिए JSON मोड वैध रहता है।
* एक बातचीत में सामग्री पाइप करने के लिए `--text -` का उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
