# एजेंट्स (Agents) के लिए omi-cli

> LLM-संचालित हार्नेस (Claude Code, Cursor, आपके अपने बॉट्स) के लिए व्यावहारिक मार्गदर्शिका।

## यह CLI एजेंट्स के लिए अनुकूल क्यों है

* **स्थिर JSON अनुबंध (Contract)।** `--json` stdout पर केवल एक वैध JSON दस्तावेज़ उत्सर्जित (emit) करता है — कोई प्रगति संदेश नहीं, कोई स्पिनर नहीं। त्रुटियाँ stderr पर `{"error": "...", "detail": "..."}` के रूप में आती हैं।
* **स्थिर निकास कोड (Exit Codes)।** `0` सफल (ok) / `1` उपयोग त्रुटि (usage) / `2` प्रमाणीकरण (auth) / `3` सर्वर त्रुटि / `4` दर सीमित (rate limited) / `5` नहीं मिला (not found)। एजेंट्स प्राकृतिक भाषा की त्रुटियों को पार्स किए बिना इन कोड्स के आधार पर आसानी से निर्णय ले सकते हैं।
* **हेडलेस (Headless) संदर्भों में कोई इंटरैक्टिव प्रॉम्प्ट नहीं।** विनाशकारी (destructive) कमांड्स में `--yes` (या `-y`) पास करें; इंटरैक्टिव लॉगिन से बचने के लिए `--api-key` पास करें या `OMI_API_KEY` सेट करें।
* **सहनशील पुनर्प्रयास (Retry) व्यवहार।** `429` और `5xx` त्रुटियों को सतह पर लाने से पहले बैकऑफ़ (backoff) के साथ स्वतः पुनः प्रयास किया जाता है।

## प्रमाणीकरण (मानव द्वारा एक बार)

उपयोगकर्ता Omi वेब ऐप (`https://app.omi.me` → Developer → API Keys) से डेवलपर API कुंजी प्राप्त करता है और इनमें से कोई एक तरीका अपनाता है:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास में दर्ज नहीं होती
# या
export OMI_API_KEY=omi_dev_...          # अल्पकालिक (ephemeral), कंटेनर-अनुकूल
```

## 5 सबसे सामान्य कार्य जो एजेंट्स करते हैं

### 1. मेमोरीज़ पढ़ें (Read memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक मेमोरी बनाएं (Create a memory)

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. वार्तालाप पढ़ें (Read conversations)

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुले कार्य आइटम पढ़ें (Read open action items)

```bash
omi action-item list --json --open
```

### 5. कार्य आइटम को पूर्ण चिह्नित करें (Mark an action item done)

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API (Local Desktop API)

जब Omi Desktop अपना स्थानीय API प्रस्तुत करता है, तो एजेंट्स क्लाउड देव API का उपयोग किए बिना डिवाइस पर स्क्रीन इतिहास, रीकैप्स, SQL और कार्यों को क्वेरी कर सकते हैं:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# या अल्पकालिक सत्रों के लिए:
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

कार्यों को केवल तभी पूर्ण या हटाएं जब उपयोगकर्ता स्पष्ट रूप से अनुरोध करे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर लिखता है और स्क्रिप्ट्स के लिए stdout पर JSON प्रिंट करता है। स्क्रीनशॉट ID आमतौर पर `local search-screen` या `screenshots` तालिका पर SQL निष्पादित करके प्राप्त होती है। यदि Desktop कोई संरचित विफलता लौटाता है जैसे `screenshot_pending`, `screenshot_file_missing`, या `screenshot_chunk_corrupted`, तो JSON मोड stderr पर `reason`, `hint`, और `screenshot_id` फ़ील्ड्स को सुरक्षित रखता है ताकि एजेंट्स किसी पुरानी ID के साथ पुनः प्रयास कर सकें या सटीक बाधा की रिपोर्ट कर सकें। दृष्टि टूल्स (vision tools) में इनपुट देने से पहले `file PATH` के साथ सफल आउटपुट को सत्यापित करें।

## कार्यशील उदाहरण: Python एजेंट लूप (Python agent loop)

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड में omi CLI को इनवोक करता है, गैर-शून्य निकास कोड पर अपवाद उठाता है।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड में stderr पर संरचित त्रुटि प्रिंट करता है:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सभी खुले कार्य आइटम पढ़ें और 30 दिनों से पुराने किसी भी आइटम को पूर्ण चिह्नित करें।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमा प्रबंधन (Handling rate limits)

मेमोरीज़: 120/घंटा। वार्तालाप: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर सीमा (rate limit) लागू हुई
    err = json.loads(result.stderr)
    # err["detail"] इस प्रकार दिखता है: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## सुझाव (Tips)

* यदि आपका एजेंट एकाधिक Omi खातों का उपयोग करता है तो `--profile <name>` का उपयोग करें। प्रत्येक प्रोफ़ाइल के अपने क्रेडेंशियल्स और API बेस होते हैं।
* स्थानीय बैकएंड परीक्षण के लिए `--api-base http://localhost:8080` का उपयोग करें।
* एकल निष्पादन के लिए प्रोफ़ाइल-विशिष्ट Desktop API सेटिंग्स को ओवरराइड करने के लिए `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` का उपयोग करें।
* डिबगिंग के लिए `--verbose` का उपयोग करें — यह stdout को प्रभावित किए बिना stderr पर `METHOD path → status (Ns)` लॉग करता है, ताकि JSON मोड की वैधता बनी रहे।
* वार्तालाप में पाइपिंग द्वारा सामग्री जोड़ने के लिए `--text -` का उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
