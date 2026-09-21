# omi-cli एजेंट लेल (Maithili / मैथिली)

> LLM-संचालित हार्नेस (Claude Code, Cursor, अपन बॉट) लेल व्यावहारिक गाइड।

## CLI एजेंट-अनुकूल कियाक अछि

* **स्थिर JSON अनुबंध (Stable JSON contract).** `--json` आउटपुट stdout पर एकटा वैध JSON दस्तावेज़ निर्गत करैत अछि आ *केबल* एकटा JSON दस्तावेज़ — कोनो प्रगति संदेश नहि, कोनो स्पिनर नहि। त्रुटि सब stderr पर `{"error": "...", "detail": "..."}` रूप में जाएत अछि।
* **स्थिर एक्ज़िट कोड (Stable exit codes).** `0` ठीक / `1` उपयोग त्रुटि / `2` प्रमाणीकरण / `3` सर्वर त्रुटि / `4` दर सीमित (rate limited) / `5` नहि भेटल। एजेंट प्राकृतिक-भाषा त्रुटि केँ पार्स केने बिना एहि पर शाखा बना सकैत अछि।
* **हेडलेस संदर्भ में कोनो इंटरैक्टिव प्रॉम्प्ट नहि (No interactive prompts in headless contexts).** विनाशकारी कमांड लेल `--yes` (वा `-y`) पास करू; इंटरैक्टिव लॉगिन छोड़य लेल `--api-key` पास करू वा `OMI_API_KEY` सेट करू।
* **माफ़ करय वला पुनः प्रयास व्यवहार (Forgiving retry behavior).** `429` आ `5xx` त्रुटि सब बैकऑफ़ कऽ कऽ पुनः प्रयास कएल जाएत अछि।

## प्रमाणीकरण (मानव द्वारा एक बेर)

उपयोगकर्ता Omi वेब ऐप (`https://app.omi.me` → Developer → API Keys) सँ एकटा डेव API कुंजी प्राप्त करैत छथि आ या तँ:

```bash
omi auth login                          # इंटरैक्टिव पेस्ट; कुंजी शेल इतिहास में नहि रहैत अछि
# वा
export OMI_API_KEY=omi_dev_...          # अल्पकालिक, कंटेनर-अनुकूल
```

## एजेंट जे पाँच काज सबसँ बेसी करैत छथि

### 1. मेमोरी पढ़ब

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एकटा मेमोरी बनाबब

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. बातचीत पढ़ब

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुला कार्य आइटम पढ़ब

```bash
omi action-item list --json --open
```

### 5. कार्य आइटम केँ पूर्ण चिन्हित करब

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटॉप API (Local Desktop API)

जब Omi Desktop अपन स्थानीय API प्रस्तुत करैत अछि, तँ एजेंट क्लाउड डेव API केँ उपयोग केने बिना ऑन-डिवाइस स्क्रीन इतिहास, रिकैप, SQL आ कार्य सब क्वेरी कऽ सकैत अछि:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# वा, अल्पकालिक सत्र लेल:
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

केबल तखने कार्य पूरा करू वा हटाउ जब उपयोगकर्ता स्पष्ट रूप सँ कहैत छथि:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट केँ डिस्क पर लिखैत अछि आ स्क्रिप्ट सब लेल stdout पर JSON प्रिंट करैत अछि। स्क्रीनशॉट ID सामान्यतः `local search-screen` वा `screenshots` तालिका पर SQL सँ आबैत अछि। यदि Desktop विफलता फेकत अछि, जेना `screenshot_pending`, `screenshot_file_missing`, वा `screenshot_chunk_corrupted`, तँ JSON मोड stderr पर `reason`, `hint`, आ `screenshot_id` फ़ील्ड सुरक्षित रखैत अछि। विज़न टूल्स केँ पास करय सँ पहिले `file PATH` सँ सफल आउटपुट केँ मान्य करू।

## व्यावहारिक उदाहरण: पाइथन एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोड में omi CLI केँ कॉल करू, असफल एक्ज़िट कोड पर अपवाद उठाउ।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोड में stderr पर संरचित त्रुटि प्रिंट करैत अछि:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सब खुला कार्य आइटम पढ़ू आ ३० दिन सँ पुरान वस्तु केँ पूर्ण चिन्हित करू।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमा नियंत्रण (Handling rate limits)

मेमोरी: 120/घंटा। बातचीत: 25/घंटा। बैच निर्माण: 15/घंटा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] एहिना देखाइ दैत अछि: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## उपयोगी सुझाव (Tips)

* यदि अहाँक एजेंट बहुत रास Omi खाता प्रबंधित करैत अछि तँ `--profile <name>` उपयोग करू। प्रत्येक प्रोफ़ाइल के अपन क्रेडेंशियल आ API बेस होइत अछि।
* स्थानीय बैकएंड परीक्षण लेल `--api-base http://localhost:8080` उपयोग करू।
* एक रन लेल प्रोफ़ाइल-स्थानीय डेस्कटॉप API सेटिंग्स ओवरराइड करय लेल `OMI_LOCAL_API_URL` आ `OMI_LOCAL_TOKEN` उपयोग करू।
* डिबगिंग लेल `--verbose` उपयोग करू — ई stdout केँ प्रभावित केने बिना stderr पर `METHOD path → status (Ns)` लॉग करैत अछि।
* बातचीत में सामग्री पाइप करय लेल `--text -` उपयोग करू:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
