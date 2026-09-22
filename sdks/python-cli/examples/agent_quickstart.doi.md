# एजेंटें लेई omi-cli

> LLM-चालित प्रणालियें (Claude Code, Cursor, तुंदे अपने बॉट्स) लेई व्यावहारिक मार्गदर्शिका।

## CLI एजेंटें लेई की जे अनुकूल ऐ

* **स्थिर JSON अनुबंध।** `--json` फ्लैग stdout पर इक मान्य JSON दस्तावेज़ ते *सिर्फ*
  JSON दस्तावेज़ आउटपुट करदा ऐ — कोई प्रगति संदेश नेईं, कोई स्पिनर नेईं। त्रुटियां
  stderr पर `{"error": "...", "detail": "..."}` रूप च जंदीयां न।
* **स्थिर निकास कोड (exit codes)।** `0` ठीक / `1` उपयोग त्रुटि / `2` प्रमाणीकरण /
  `3` सर्वर त्रुटि / `4` अनुरोध सीमा (rate limited) / `5` नेईं लब्भा। एजेंट प्राकृतिक
  भाषा त्रुटियें दा विश्लेषण कीते बगैर सीधे इनें कोडें पर निर्णय लै सकदे न।
* **हेडलेस संदर्भें च कोई इंटरैक्टिव प्रॉम्प्ट नेईं।** बदलाव करने आहले कमांडें गी
  `--yes` (जां `-y`) दित्ता जा; इंटरैक्टिव लॉगिन गी छड्डने लेई `--api-key` दित्ता जा जां `OMI_API_KEY` सेट करो।
* **लचीला पुनः प्रयास व्यवहार।** `429` ते `5xx` त्रुटियां दिखने थमां पैह्ले
  क्रमिक देरी (backoff) कन्ने अपने-आप दुबारा प्रयास कीतीयां जंदीयां न।

## प्रमाणीकरण (इक बारी, मानव आसेआ)

उपयोगकर्ता Omi वेब ऐप थमां डेवलपर API कुंजी हासिल करदा ऐ
(`https://app.omi.me` → Developer → API Keys) ते इनें च इक चुनदा ऐ:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास च नेईं रोंह्दी
# जां
export OMI_API_KEY=omi_dev_...          # अल्पकालिक, कंटेनर अनुकूल
```

## पंज मुख्य कम्म जेह्ड़े एजेंट सबने शा मते करदे न

### 1. यादां पढ़ब

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. याद बनाब

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. गल्लबातां पढ़ब

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुह्ले कम्म-काज पढ़ब

```bash
omi action-item list --json --open
```

### 5. कम्म गी पूरा चिह्नित करब

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API (Local Desktop API)

जदू Omi Desktop अपना स्थानीय API सक्रिय करदा ऐ, तदू एजेंट क्लाउड डेवलपर API दा
उपयोग कीते बगैर डिवाइस दी स्क्रीन इतिहास, सारांश, SQL डेटा ते कम्म पुच्छी सकदे न:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# जां अल्पकालिक सत्रें लेई:
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

कम्में गी सिर्फ तदू पूरा करो जां मिटाओ जदू उपयोगकर्ता स्पष्ट रूप कन्ने पुच्छे:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट गी डिस्क पर लिखदा ऐ ते
स्क्रिप्टें लेई stdout पर JSON आउटपुट जारी रखदा ऐ। स्क्रीनशॉट आईडी सामान्यतः
`local search-screen` जां `screenshots` तालिका पर SQL क्वेरी थमां लब्भदी ऐ। जेकर Desktop
`screenshot_pending`, `screenshot_file_missing` जां `screenshot_chunk_corrupted` जिस्सा
संरचित विफलता दिन्दा ऐ, तां JSON मोड stderr पर `reason`, `hint` ते `screenshot_id` फ़ील्ड
सुरक्षित रखदा ऐ तांदे एजेंट पुरानी आईडी कन्ने दुबारा प्रयास करी सकन जां सही बाधा गी दस्सी सकन।
सफल आउटपुट गी विज़न टूल्स च भेजने थमां पैह्ले `file PATH` कन्ने सत्यापित करो।

## व्यावहारिक उदाहरण: Python एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड च omi CLI गी आह्वान करदा ऐ, विफलता पर अपवाद चकदा ऐ।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड च stderr पर संरचित त्रुटियां कढ्ढदा ऐ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सारे खुह्ले कम्म पढ़ो ते 30 दिने थमां पुराने सारे कम्में गी पूरा चिह्नित करो।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## अनुरोध सीमाएं दा प्रबंधन (Rate Limits)

यादां: 120/घंटे। गल्लबातां: 25/घंटे। बैच निर्माण: 15/घंटे।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # अनुरोध सीमा पूरी होई गेई
    err = json.loads(result.stderr)
    # err["detail"] इस चाल्ली दिखेआ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## उपयोगी सुझाव

* जेकर तुंदा एजेंट मते Omi खाते संभाल्दा ऐ, तां `--profile <name>` दा उपयोग करो।
  हर प्रोफाइल दा अपना क्रेडेंशियल ते आधार API होंदा ऐ।
* स्थानीय बैकएंड परीक्षण लेई `--api-base http://localhost:8080` दा उपयोग करो।
* इक बारी चलाने लेई प्रोफाइल दे स्थानीय Desktop API सेटिंग्स गी ओवरराइड करने लेई
  `OMI_LOCAL_API_URL` ते `OMI_LOCAL_TOKEN` दा उपयोग करो।
* डिबगिंग लेई `--verbose` दा उपयोग करो — एह stdout गी प्रभावित कीते बगैर stderr पर
  `METHOD path → status (Ns)` लॉग करदा ऐ, जिंदे कन्ने JSON मोड मान्य रोंह्दा ऐ।
* गल्लबात च सामग्री पाइप करने लेई `--text -` दा उपयोग करो:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
