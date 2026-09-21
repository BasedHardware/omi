# एजंट्ससाठी omi-cli

> LLM-चालित एजंट वातावरणासाठी (Claude Code, Cursor, तुमचे स्वतःचे बॉट) व्यावहारिक मार्गदर्शक।

## CLI एजंट-अनुकूल का आहे

* **स्थिर JSON करार.** `--json` stdout वर वैध JSON दस्तऐवज देतो आणि
  *फक्त* JSON दस्तऐवज — कोणतेही प्रगती संदेश नाहीत, कोणतेही स्पिनर नाहीत.
  त्रुटी stderr वर `{"error": "...", "detail": "..."}` स्वरूपात जातात.
* **स्थिर एक्झिट कोड.** `0` यशस्वी / `1` चुकीचा वापर / `2` प्रमाणीकरण /
  `3` सर्व्हर / `4` दर-मर्यादित / `5` सापडले नाही. एजंट्स नैसर्गिक-भाषेतील
  त्रुटींचे विश्लेषण न करता या कोडवर शाखा करू शकतात.
* **हेडलेस संदर्भात कोणतेही परस्परसंवादी प्रॉम्प्ट नाहीत.** विध्वंसक आदेशांसाठी
  `--yes` (किंवा `-y`) द्या; परस्परसंवादी लॉगिन टाळण्यासाठी `--api-key` द्या
  किंवा `OMI_API_KEY` सेट करा.
* **सहनशील पुन्हा-प्रयत्न वर्तन.** `429` आणि `5xx` समोर येण्यापूर्वी बॅकऑफसह
  पुन्हा प्रयत्न केला जातो.

## प्रमाणीकरण (एकदा, माणसाकडून)

वापरकर्ता Omi वेब अ‍ॅप (`https://app.omi.me` → Developer → API Keys) कडून डेव्ह API
की मिळवतो आणि यापैकी एक पर्याय निवडतो:

```bash
omi auth login                          # परस्परसंवादी पेस्ट; की shell इतिहासात राहत नाही
# किंवा
export OMI_API_KEY=omi_dev_...          # तात्पुरती, कंटेनर-अनुकूल
```

## एजंट्स सर्वाधिक करतात त्या पाच गोष्टी

### 1. स्मृती वाचा

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. स्मृती तयार करा

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. संभाषणे वाचा

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. खुल्या अ‍ॅक्शन आयटम्स वाचा

```bash
omi action-item list --json --open
```

### 5. अ‍ॅक्शन आयटम पूर्ण करा

```bash
omi action-item complete --json a1b2c3d4
```

## लोकल डेस्कटॉप API

Omi Desktop त्याचे लोकल API उघड करतो तेव्हा, एजंट्स क्लाउड डेव्ह API न वापरता
डिव्हाइसवरील स्क्रीन इतिहास, सारांश, SQL आणि कार्ये क्वेरी करू शकतात:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# किंवा, तात्पुरत्या सत्रांसाठी:
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

वापरकर्त्याने स्पष्टपणे सांगितल्याशिवाय कार्ये पूर्ण करू नका किंवा हटवू नका:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट डिस्कवर लिहितो आणि
स्क्रिप्ट्ससाठी stdout वर JSON प्रिंट करतो. स्क्रीनशॉट आयडी सामान्यतः
`local search-screen` किंवा `screenshots` टेबलावरील SQL मधून येतो. Desktop ने
`screenshot_pending`, `screenshot_file_missing` किंवा `screenshot_chunk_corrupted`
सारखे संरचित अपयश दिल्यास, JSON मोड stderr वर `reason`, `hint` आणि
`screenshot_id` फील्ड्स जपतो, जेणेकरून एजंट्स जुन्या आयडीसह पुन्हा प्रयत्न करू
शकतात किंवा नेमका अडथळा नोंदवू शकतात. यशस्वी आउटपुट व्हिजन टूल्सना पाठवण्यापूर्वी
`file PATH` ने तपासा.

## कार्यप्रवाह उदाहरण: Python एजंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI JSON मोडमध्ये चालवतो, अयशस्वी एक्झिट कोडवर अपवाद उचलतो."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोडमध्ये stderr वर संरचित त्रुटी प्रिंट करतो:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सर्व खुल्या अ‍ॅक्शन आयटम्स वाचा आणि 30 दिवसांपेक्षा जुने पूर्ण करा.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर मर्यादा हाताळणे

स्मृती: 120/तास. संभाषणे: 25/तास. बॅच निर्मिती: 15/तास.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर-मर्यादित
    err = json.loads(result.stderr)
    # err["detail"] असे दिसते: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## टिप्स

* तुमचा एजंट एकाधिक Omi खाती सांभाळत असेल तर `--profile <name>` वापरा. प्रत्येक
  प्रोफाइलची स्वतःची क्रेडेन्शियल्स आणि API बेस असतो.
* लोकल बॅकएंड चाचणीसाठी `--api-base http://localhost:8080` वापरा.
* एका रनसाठी प्रोफाइल-लोकल Desktop API सेटिंग्ज ओव्हरराइड करण्यासाठी
  `OMI_LOCAL_API_URL` आणि `OMI_LOCAL_TOKEN` वापरा.
* डीबगिंगसाठी `--verbose` वापरा — ते stderr वर `METHOD path → status (Ns)`
  लॉग करते, stdout वर परिणाम न करता, त्यामुळे JSON मोड वैध राहतो.
* पाइपद्वारे संभाषणात सामग्री पाठवण्यासाठी `--text -` वापरा:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
