# एजेंट्स के लिए omi-cli

> एलएलएम (LLM) आधारित परिवेशों (Claude Code, Cursor, आपके अपने बॉट्स) के लिए व्यावहारिक मार्गदर्शिका।

## एजेंट्स के लिए CLI क्यों आदर्श है

* **स्थिर JSON अनुबंध।** `--json` फ्लैग `stdout` पर केवल एक मान्य JSON दस्तावेज़
  आउटपुट करता है: कोई प्रगति संदेश या लोडिंग स्पिनर नहीं। त्रुटियाँ `stderr` पर
  `{"error": "...", "detail": "..."}` के रूप में भेजी जाती हैं।
* **स्थिर निकास कोड (Exit Codes)।** `0` सफलता / `1` उपयोग त्रुटि / `2` प्रमाणीकरण / `3` सर्वर / `4` दर सीमा
  (rate limit) / `5` नहीं मिला। एजेंट्स प्राकृतिक भाषा की त्रुटियों को पार्स किए बिना इन कोडों के आधार पर निर्णय ले सकते हैं।
* **हेडलेस संदर्भों में कोई इंटरैक्टिव प्रॉम्प्ट नहीं।** विनाशकारी आदेशों के लिए `--yes` (या `-y`) पास करें;
  इंटरैक्टिव लॉगिन को छोड़ने के लिए `--api-key` पास करें या `OMI_API_KEY` सेट करें।
* **पुनर्प्रयास (Retry) की सुविधा।** `429` और `5xx` त्रुटियों को प्रदर्शित करने से पहले घातीय बैकऑफ़ के साथ
  स्वचालित रूप से पुनः प्रयास किया जाता है।

## प्रमाणीकरण (केवल एक बार, उपयोगकर्ता द्वारा)

उपयोगकर्ता Omi वेब ऐप (`https://app.omi.me` → Developer → API Keys) से डेवलपर API कुंजी प्राप्त करता है
और निम्न में से कोई एक विकल्प चुनता है:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास में नहीं रहती
# या
export OMI_API_KEY=omi_dev_...          # अल्पकालिक, कंटेनरों के लिए आदर्श
```

## एजेंट्स के लिए 5 सबसे आम कार्य

### 1. यादें (Memories) पढ़ना

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक याद बनाना

```bash
omi memory create --json "उपयोगकर्ता डार्क मोड पसंद करता है" --category lifestyle
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

## डेस्कटॉप स्थानीय API

जब Omi Desktop अपना स्थानीय API सक्षम करता है, तो एजेंट्स क्लाउड डेवलपर API का उपयोग किए बिना
डिवाइस पर स्क्रीन इतिहास, सारांश, SQL और कार्यों की जानकारी प्राप्त कर सकते हैं:

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

कार्यों को केवल तभी पूर्ण या हटाएं जब उपयोगकर्ता ने स्पष्ट रूप से ऐसा करने का अनुरोध किया हो:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट को डिस्क पर सहेजता है और
स्क्रिप्ट के लिए `stdout` पर JSON प्रिंट करना जारी रखता है। स्क्रीनशॉट आईडी आमतौर पर
`local search-screen` या `screenshots` तालिका पर SQL क्वेरी से प्राप्त होती है। यदि डेस्कटॉप
`screenshot_pending`, `screenshot_file_missing` या `screenshot_chunk_corrupted` जैसी
त्रुटि देता है, तो JSON मोड `stderr` पर `reason`, `hint` और `screenshot_id` फ़ील्ड सुरक्षित रखता है
ताकि एजेंट्स पिछली आईडी के साथ पुनः प्रयास कर सकें। विज़न टूल्स में पास करने से पहले `file PATH` के साथ
सफल आउटपुट सत्यापित करें।

## व्यावहारिक उदाहरण: Python में एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड में omi CLI को कॉल करता है, गैर-शून्य निकास कोड पर अपवाद उत्पन्न करता है।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड में stderr पर संरचित त्रुटियां प्रिंट करता है:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi कोड {result.returncode} के साथ समाप्त हुआ: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सभी खुले कार्य पढ़ें और 30 दिन से अधिक पुराने कार्यों को पूर्ण चिह्नित करें।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमा (Rate Limits) संभालना

यादें: 120/घंटा। बातचीत: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर सीमा समाप्त
    err = json.loads(result.stderr)
    # err["detail"] का प्रारूप: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## सुझाव

* यदि आपका एजेंट कई Omi खातों का प्रबंधन करता है तो `--profile <name>` का उपयोग करें। प्रत्येक
  प्रोफ़ाइल अपने स्वयं के क्रेडेंशियल और API बेस रखता है।
* स्थानीय बैकएंड परीक्षण के लिए `--api-base http://localhost:8080` का उपयोग करें।
* एकल निष्पादन के लिए प्रोफ़ाइल के डेस्कटॉप स्थानीय API को ओवरराइड करने हेतु `OMI_LOCAL_API_URL` और `OMI_LOCAL_TOKEN` का उपयोग करें।
* डिबगिंग के लिए `--verbose` का उपयोग करें: यह `stdout` को प्रभावित किए बिना `stderr` पर
  `METHOD path status (Ns)` लॉग करता है, जिससे JSON स्ट्रीम सुरक्षित रहता है।
* पाइप के माध्यम से बातचीत सामग्री भेजने के लिए `--text -` का उपयोग करें:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
