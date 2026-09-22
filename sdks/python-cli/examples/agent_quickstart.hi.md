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

कार्यों को केवल तभी पूरा करें या हटाएं जब उपयोगकर्ता स्पष्ट रूप से अनुरोध करे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर लिखता है और स्क्रिप्ट के लिए stdout पर JSON प्रिंट करता है। स्क्रीनशॉट ID आमतौर पर `local search-screen` या `screenshots` टेबल पर SQL से मिलती है। यदि Desktop कोई संरचित विफलता लौटाता है जैसे `screenshot_pending`, `screenshot_file_missing`, या `screenshot_chunk_corrupted`, तो JSON मोड stderr पर `reason`, `hint`, और `screenshot_id` फ़ील्ड को सुरक्षित रखता है ताकि एजेंट पुरानी ID के साथ पुनः प्रयास कर सकें या सटीक समस्या की रिपोर्ट कर सकें। विज़न टूल्स में पास करने से पहले `file PATH` के साथ सफल आउटपुट को सत्यापित करें।

## व्यावहारिक उदाहरण: पायथन (Python) एजेंट लूप

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

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमा प्रबंधन (Handling rate limits)

यादें: 120/घंटा। बातचीत: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## उपयोगी सुझाव (Tips)

* यदि आपका एजेंट कई Omi खाते संभालता है तो `--profile <name>` का उपयोग करें। प्रत्येक प्रोफ़ाइल के अपने क्रेडेंशियल्स और API बेस होते हैं।
* स्थानीय बैकएंड परीक्षण के लिए `--api-base http://localhost:8080` का उपयोग करें।
* एक रन के लिए प्रोफ़ाइल की स्थानीय Desktop API सेटिंग्स को ओवरराइड करने हेतु `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` का उपयोग करें।
* डीबगिंग के लिए `--verbose` का उपयोग करें — यह stdout को प्रभावित किए बिना stderr पर `METHOD path → status (Ns)` लॉग करता है, ताकि JSON मोड वैध रहे।
* पाइप के माध्यम से बातचीत में सामग्री भेजने के लिए, `--text -` का उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
