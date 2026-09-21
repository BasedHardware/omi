# एजेंट्स लेल omi-cli

> LLM-संचालित प्रणाली (Claude Code, Cursor, अहाँक अपन बॉट्स) लेल व्यावहारिक मार्गदर्शिका।

## CLI एजेंट्स लेल किएक अनुकूल अछि

* **स्थिर JSON अनुबंध।** `--json` फ्लैग stdout पर एकटा मान्य JSON दस्तावेज़ आ *मात्र*
  JSON दस्तावेज़ आउटपुट करैत अछि — कोनो प्रगति संदेश नहि, कोनो स्पिनर नहि। त्रुटि सभ
  stderr पर `{"error": "...", "detail": "..."}` रूप मे जाइत अछि।
* **स्थिर निकास कोड (exit codes)।** `0` सफल / `1` उपयोग त्रुटि / `2` प्रमाणीकरण /
  `3` सर्वर त्रुटि / `4` अनुरोध सीमा (rate limited) / `5` नहि भेटल। एजेंट्स बिना
  प्राकृतिक भाषा त्रुटि विश्लेषण कएने सोझे एहि कोड सभ पर निर्णय लऽ सकैत छथि।
* **हेडलेस परिवेश मे कोनो इंटरैक्टिव प्रॉम्प्ट नहि।** परिवर्तनकारी कमांड सभ मे
  `--yes` (अथवा `-y`) लगाउ; इंटरैक्टिव लॉगिन छोड़बाक लेल `--api-key` दिअ अथवा `OMI_API_KEY` सेट करू।
* **लचीला पुनः प्रयास व्यवहार।** `429` आ `5xx` त्रुटि सभ प्रदर्शित होमय सँ पहिने
  स्वतः क्रमिक विलंब (backoff) सँग पुनः प्रयास कएल जाइत अछि।

## प्रमाणीकरण (एक बेर, मानव द्वारा)

उपयोगकर्ता Omi वेब ऐप सँ डेवलपर API कुंजी प्राप्त करैत छथि
(`https://app.omi.me` → Developer → API Keys) आ निम्नलिखित मे सँ एकटा चुनैत छथि:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास मे नहि रहैत अछि
# अथवा
export OMI_API_KEY=omi_dev_...          # क्षणिक, कंटेनर अनुकूल
```

## पाँच प्रमुख काज जे एजेंट्स सबसँ बेसी करैत छथि

### 1. स्मृति सभ पढ़ब

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. नव स्मृति बनएब

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. बातचीत सभ पढ़ब

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुला कार्य बिंदु पढ़ब

```bash
omi action-item list --json --open
```

### 5. कार्य बिंदु कए पूर्ण चिह्नित करब

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API (Local Desktop API)

जखन Omi Desktop अपन स्थानीय API सक्रिय करैत अछि, तखन एजेंट्स बिना क्लाउड डेवलपर API क
उपयोग कएने डिवाइसक स्क्रीन इतिहास, सारांश, SQL डेटा आ कार्य सभ प्राप्त कऽ सकैत छथि:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# अथवा क्षणिक सत्र लेल:
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

कार्य सभ कए तखने पूर्ण अथवा विलोपित करू जखन उपयोगकर्ता स्पष्ट रूप सँ अनुरोध करथि:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट कए डिस्क पर लिखैत अछि आ
स्क्रिप्ट सभ लेल stdout पर JSON आउटपुट जारी रखैत अछि। स्क्रीनशॉट आईडी सामान्यतः
`local search-screen` अथवा `screenshots` तालिका पर SQL क्वेरी सँ भेटैत अछि। यदि Desktop
`screenshot_pending`, `screenshot_file_missing` अथवा `screenshot_chunk_corrupted` जकाँ
संरचित विफलता दैत अछि, तँ JSON मोड stderr पर `reason`, `hint` आ `screenshot_id` फ़ील्ड
सुरक्षित रखैत अछि जाहि सँ एजेंट्स पुरान आईडी सँ पुनः प्रयास कऽ सकथि अथवा सही बाधा सूचित कऽ सकथि।
सफल आउटपुट कए विज़न टूल्स मे पठेबा सँ पहिने `file PATH` सँ सत्यापित करू।

## व्यावहारिक उदाहरण: Python एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड मे omi CLI कए आह्वान करैत अछि, असफलता पर अपवाद उठबैत अछि।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड मे stderr पर संरचित त्रुटि आउटपुट करैत अछि:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सभ खुला कार्य बिंदु पढ़ू आ 30 दिन सँ पुरान सभटा कए पूर्ण चिह्नित करू।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## अनुरोध सीमाक प्रबंधन (Rate Limits)

स्मृति: 120/घंटा। बातचीत: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # अनुरोध सीमा समाप्त
    err = json.loads(result.stderr)
    # err["detail"] एहि रूप मे देखाइत अछि: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## उपयोगी सुझाव

* यदि अहाँक एजेंट बहुत रास Omi खाताक प्रबंधन करैत अछि, तँ `--profile <name>` क उपयोग करू।
  प्रत्येक प्रोफाइलक अपन क्रेडेंशियल आ आधार API होइत अछि।
* स्थानीय बैकएंड परीक्षण लेल `--api-base http://localhost:8080` क उपयोग करू।
* एक बेर क रन लेल प्रोफाइलक स्थानीय Desktop API सेटिंग्स कए ओवरराइड करवाक लेल
  `OMI_LOCAL_API_URL` आ `OMI_LOCAL_TOKEN` क उपयोग करू।
* डीबगिंग लेل `--verbose` क उपयोग करू — ई stdout कए प्रभावित कएने बिना stderr पर
  `METHOD path → status (Ns)` लॉग करैत अछि, जाहि सँ JSON मोड मान्य रहैत अछि।
* बातचीत मे सामग्री पाइप करवाक लेल `--text -` क उपयोग करू:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
