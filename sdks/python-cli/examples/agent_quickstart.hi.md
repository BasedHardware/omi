# एजेंट्स के लिए omi-cli

> LLM-संचालित हार्नेस (Claude Code, Cursor, आपके अपने बॉट) के लिए व्यावहारिक मार्गदर्शिका।

## CLI एजेंट-अनुकूल क्यों है

* **स्थिर JSON अनुबंध।** `--json` stdout पर केवल एक वैध JSON दस्तावेज़ उत्सर्जित करता है और
  *केवल* एक JSON दस्तावेज़ — कोई प्रगति संदेश नहीं, कोई स्पिनर नहीं। त्रुटियाँ
  stderr पर `{"error": "...", "detail": "..."}` के रूप में जाती हैं।
* **स्थिर एग्जिट कोड।** `0` ठीक / `1` उपयोग / `2` प्रमाणीकरण / `3` सर्वर / `4` रेट
  सीमित / `5` नहीं मिला। एजेंट प्राकृतिक-भाषा त्रुटियों को पार्स किए बिना
  इनके आधार पर शाखा (branch) बना सकते हैं।
* **हेडलेस संदर्भों में कोई इंटरैक्टिव प्रॉम्प्ट नहीं।** विनाशकारी (destructive) कमांड में
  `--yes` (या `-y`) पास करें; इंटरैक्टिव लॉगिन छोड़ने के लिए `--api-key` पास करें
  या `OMI_API_KEY` सेट करें।
* **उदार पुनः-प्रयास व्यवहार।** `429` और `5xx` को सतह पर आने से पहले
  बैकऑफ के साथ पुनः-प्रयास किया जाता है।

## प्रमाणीकरण (एक बार, इंसान द्वारा)

उपयोगकर्ता Omi वेब ऐप से एक डेवलपर API कुंजी प्राप्त करता है
(`https://app.omi.me` → Developer → API Keys) और या तो:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## एजेंट्स जो सबसे अधिक करते हैं वे पाँच कार्य

### 1. स्मृतियाँ (memories) पढ़ें

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक स्मृति बनाएँ

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. वार्तालाप (conversations) पढ़ें

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुले एक्शन आइटम पढ़ें

```bash
omi action-item list --json --open
```

### 5. किसी एक्शन आइटम को पूर्ण चिह्नित करें

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API

जब Omi Desktop अपनी स्थानीय API उजागर करता है, एजेंट क्लाउड डेवलपर API का उपयोग किए
बिना डिवाइस-पर स्क्रीन इतिहास, रीकैप, SQL और कार्यों को क्वेरी कर सकते हैं:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

कार्यों को केवल तब पूर्ण या हटाएँ जब उपयोगकर्ता स्पष्ट रूप से कहे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर
लिखता है और स्क्रिप्ट्स के लिए stdout पर JSON भी प्रिंट करता है। स्क्रीनशॉट आईडी
आमतौर पर `local search-screen` या `screenshots` टेबल पर SQL से आती है। यदि Desktop
`reason`, `hint`, और `screenshot_id` फ़ील्ड्स को stderr पर संरक्षित रखता है ताकि एजेंट
पुरानी आईडी का पुनः-प्रयास कर सकें या सटीक अवरोध की रिपोर्ट कर सकें। विज़न टूल्स को
देने से पहले सफल आउटपुट को `file PATH` से मान्य करें।

## कार्यरत उदाहरण: Python एजेंट लूप

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

## रेट सीमाओं को संभालना

स्मृतियाँ: 120/घंटा। वार्तालाप: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## सुझाव

* यदि आपका एजेंट कई Omi खातों को संभालता है तो `--profile <name>` का उपयोग करें।
  प्रत्येक प्रोफ़ाइल की अपनी क्रेडेंशियल और API बेस होती है।
* स्थानीय बैकएंड परीक्षण के लिए `--api-base http://localhost:8080` का उपयोग करें।
* एक रन के लिए प्रोफ़ाइल-स्थानीय डेस्कटॉप API सेटिंग्स को ओवरराइड करने हैं तो
  `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` का उपयोग करें।
* डीबगिंग के लिए `--verbose` का उपयोग करें — यह stderr पर
  `METHOD path → status (Ns)` लॉग करता है, stdout को प्रभावित किए बिना, ताकि
  JSON मोड मान्य रहे।
* किसी वार्तालाप में कंटेंट पाइप करने के लिए `--text -` का उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
