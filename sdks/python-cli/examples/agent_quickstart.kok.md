# एजेंटां खातीर omi-cli

> LLM-चालित हार्नेसां खातीर (Claude Code, Cursor, तुमचे स्वताचे बॉट) व्यवहारीक मार्गदर्शक.

## हो CLI एजेंट-अनुकूल कित्याक आसा

* **स्थिर JSON करार.** `--json` stdout-ार एक वैध JSON दस्तावेज दिता आनी
  *फकत* एक JSON दस्तावेज — प्रगती संदेश ना, स्पिनर ना. त्रुटी
  stderr-ार `{"error": "...", "detail": "..."}` अशा स्वरूपांत वतात.
* **स्थिर एक्झिट कोड.** `0` यशस्वी / `1` वापर / `2` प्रमाणीकरण / `3` सर्व्हर /
  `4` दर-मर्यादा / `5` सापडना. एजेंट नैसर्गिक-भाशेच्यो त्रुटी वाचन करिनास्तना
  ह्या कोडांचेर शाखा करूं शकतात.
* **हेडलेस संदर्भांनी इंटरॅक्टिव्ह प्रॉम्प्ट ना.** विनाशकारी कमांडांक
  `--yes` (वा `-y`) दिवचो; इंटरॅक्टिव्ह लॉगिन टाळपाक `--api-key` दिवचो वा
  `OMI_API_KEY` सेट करचो.
* **सोसणारें पुन्हा-प्रयत्न वर्तन.** `429` आनी `5xx` आयच्या आदीं
  बॅकऑफसयत पुन्हा प्रयत्न जाता.

## प्रमाणीकरण (एकदां, मनशान)

वापरपी Omi वेब अॅप (`https://app.omi.me` → Developer → API Keys) कडल्यान डेव्ह API
की घेता आनी ह्यांतलो एक वाट काडटा:

```bash
omi auth login                          # इंटरॅक्टिव्ह पेस्ट; की shell इतिहासांत उरना
# वा
export OMI_API_KEY=omi_dev_...          # तात्पुरती, कंटेनर-अनुकूल
```

## एजेंट सर्वाधिक करतात तीं पांच कामां

### 1. स्मृती वाचात

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. एक स्मृति तयार करात

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. संवाद वाचात

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. उक्त क्रिया-आयटम वाचात

```bash
omi action-item list --json --open
```

### 5. क्रिया-आयटम पूर्ण म्हणून निशाण करात

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानिक Desktop API

जेन्ना Omi Desktop ताचें स्थानिक API उक्तें करता, तेन्ना एजेंट क्लाउड डेव्ह API वापरिनास्तना
डिव्हायसांतलो स्क्रीन इतिहास, पुनरावलोकनां, SQL आनी कार्यां विचारूं शकतात:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# वा, तात्पुरत्या सत्रांक:
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

वापरप्यान स्पश्टपणान सांगल्यारच कार्यां पूर्ण करचीं वा काडचीं:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` स्क्रीनशॉट डिस्काचेर बरयता आनी
स्क्रिप्टांक खातीर stdout-ार JSON छापता. स्क्रीनशॉट आयडी चड करून `local search-screen`
वा `screenshots` टेबलाचेर SQL कडल्यान येता. जर Desktop `screenshot_pending`,
`screenshot_file_missing` वा `screenshot_chunk_corrupted` सारखें रचनात्मक अयशस्वी परत
दिता, तर JSON मोड stderr-ार `reason`, `hint` आनी `screenshot_id` फील्ड राखता, जेणेकरून
एजेंट पोरनी आयडी वापरून पुन्हा प्रयत्न करूं शकतात वा नेमकी अडचण कळूं शकतात. यशस्वी
आउटपुट विझन साधनांक दिवच्या आदीं `file PATH` वापरून तपासात.

## केल्लो उदाहरण: Python एजेंट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI JSON मोडांत आपयात; यशस्वी नाशिल्ल्या एक्झिट कोडांचेर त्रुटी उबारता."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON मोडांत stderr-ार रचनात्मक त्रुटी छापता:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सगळीं उक्त क्रिया-आयटम वाचात आनी 30 दिसां परस पोरनिं पूर्ण म्हणून निशाण करात.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर-मर्यादा हाताळप

स्मृती: 120/वर। संवाद: 25/वर। बॅच तयारी: 15/वर।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर-मर्यादा
    err = json.loads(result.stderr)
    # err["detail"] अशें दिसता: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## सूच

* तुमचो एजेंट जर खूब Omi खातीं हाताळटा तर `--profile <name>` वापरात. दरेका
  प्रोफायलाचे स्वताचे प्रमाणपत्र आनी API बेस आसता.
* स्थानिक बॅकएंड चांचणी खातीर `--api-base http://localhost:8080` वापरात.
* एका धावेखातीर प्रोफायल-स्थानिक Desktop API सेटिंगां बदलपाक `OMI_LOCAL_API_URL`
  आनी `OMI_LOCAL_TOKEN` वापरात.
* डीबगिंग खातीर `--verbose` वापरात — तो stderr-ार `METHOD path → status (Ns)` लॉग
  करता, stdout-ार परिणाम करना, देखून JSON मोड वैध उरता.
* संवादांत मजकूर पाइप करपाक `--text -` वापरात:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
