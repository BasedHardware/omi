# এজেন্টদের জন্য omi-cli

> LLM-চালিত এজেন্ট পরিবেশের (Claude Code, Cursor, আপনার নিজের বট) জন্য ব্যবহারিক গাইড।

## কেন CLI এজেন্ট-বান্ধব

* **স্থিতিশীল JSON কনট্র্যাক্ট।** `--json` stdout-এ একটি বৈধ JSON ডকুমেন্ট দেয় এবং
  *শুধুমাত্র* একটি JSON ডকুমেন্ট — কোনো অগ্রগতি বার্তা নেই, কোনো স্পিনার নেই। ত্রুটিগুলো
  stderr-এ `{"error": "...", "detail": "..."}` আকারে যায়।
* **স্থিতিশীল এক্সিট কোড।** `0` সফল / `1` ভুল ব্যবহার / `2` প্রমাণীকরণ /
  `3` সার্ভার / `4` রেট সীমিত / `5` পাওয়া যায়নি। এজেন্টরা প্রাকৃতিক-ভাষার
  ত্রুটি পার্স না করেই এই কোডগুলোর উপর শাখা করতে পারে।
* **হেডলেস প্রেক্ষাপটে কোনো ইন্টারঅ্যাকটিভ প্রম্পট নেই।** ধ্বংসাত্মক কমান্ডে
  `--yes` (বা `-y`) দিন; ইন্টারঅ্যাকটিভ লগইন এড়াতে `--api-key` দিন
  বা `OMI_API_KEY` সেট করুন।
* **ক্ষমাশীল রিট্রাই আচরণ।** `429` এবং `5xx` দেখানোর আগে ব্যাকঅফসহ আবার
  চেষ্টা করা হয়।

## প্রমাণীকরণ (একবার, মানুষের দ্বারা)

ব্যবহারকারী Omi ওয়েব অ্যাপ
(`https://app.omi.me` → Developer → API Keys) থেকে একটি ডেভ API কী নেন এবং
যেকোনো একটি উপায় বেছে নেন:

```bash
omi auth login                          # ইন্টারঅ্যাকটিভ পেস্ট; কী shell ইতিহাসে থাকে না
# অথবা
export OMI_API_KEY=omi_dev_...          # ক্ষণস্থায়ী, কন্টেইনার-বান্ধব
```

## এজেন্টরা সবচেয়ে বেশি যেগুলো করে

### ১. মেমরি পড়ুন

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### ২. একটি মেমরি তৈরি করুন

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### ৩. কথোপকথন পড়ুন

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ৪. খোলা অ্যাকশন আইটেম পড়ুন

```bash
omi action-item list --json --open
```

### ৫. একটি অ্যাকশন আইটেম সম্পন্ন করুন

```bash
omi action-item complete --json a1b2c3d4
```

## লোকাল ডেস্কটপ API

যখন Omi Desktop তার লোকাল API প্রকাশ করে, এজেন্টরা ক্লাউড ডেভ API ব্যবহার না করেই
ডিভাইসের স্ক্রিন ইতিহাস, রিক্যাপ, SQL এবং টাস্ক কুয়েরি করতে পারে:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# অথবা, ক্ষণস্থায়ী সেশনের জন্য:
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

ব্যবহারকারী স্পষ্টভাবে না বললে টাস্ক সম্পন্ন বা মুছবেন না:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` স্ক্রিনশটটি ডিস্কে লেখে এবং
স্ক্রিপ্টের জন্য stdout-এ JSON প্রিন্ট করে। স্ক্রিনশট আইডি সাধারণত
`local search-screen` বা `screenshots` টেবিলের SQL থেকে আসে। Desktop যদি
`screenshot_pending`, `screenshot_file_missing`, বা `screenshot_chunk_corrupted`-এর মতো
স্ট্রাকচার্ড ব্যর্থতা ফেরত দেয়, JSON মোড stderr-এ `reason`, `hint`, এবং
`screenshot_id` ফিল্ড সংরক্ষণ করে যাতে এজেন্টরা পুরনো আইডি দিয়ে আবার চেষ্টা করতে
বা সঠিক বাধাটি রিপোর্ট করতে পারে। ভিশন টুলে পাঠানোর আগে সফল আউটপুট
`file PATH` দিয়ে যাচাই করুন।

## কার্যপ্রবাহের উদাহরণ: Python এজেন্ট লুপ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON মোডে omi CLI চালায়, সফল না হলে নন-জিরো এক্সিট কোডে ত্রুটি তোলে।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON মোডে stderr-এ স্ট্রাকচার্ড ত্রুটি প্রিন্ট করে:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# সমস্ত খোলা অ্যাকশন আইটেম পড়ুন এবং ৩০ দিনের পুরনো যেকোনোটি সম্পন্ন করুন।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## রেট সীমা সামলানো

মেমরি: 120/ঘণ্টা। কথোপকথন: 25/ঘণ্টা। ব্যাচ তৈরি: 15/ঘণ্টা।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # রেট সীমিত
    err = json.loads(result.stderr)
    # err["detail"] দেখতে যেমন হয়: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## টিপস

* আপনার এজেন্ট যদি একাধিক Omi অ্যাকাউন্ট সামলায় তাহলে `--profile <name>` ব্যবহার করুন।
  প্রতিটি প্রোফাইলের নিজস্ব ক্রেডেনশিয়াল এবং API বেস থাকে।
* লোকাল ব্যাকএন্ড পরীক্ষার জন্য `--api-base http://localhost:8080` ব্যবহার করুন।
* এক রানের জন্য প্রোফাইল-লোকাল Desktop API সেটিংস ওভাররাইড করতে
  `OMI_LOCAL_API_URL` এবং `OMI_LOCAL_TOKEN` ব্যবহার করুন।
* ডিবাগিংয়ের জন্য `--verbose` ব্যবহার করুন — এটি stderr-এ
  `METHOD path → status (Ns)` লগ করে stdout-কে অপরিবর্তিত রাখে, ফলে JSON মোড
  বৈধ থাকে।
* পাইপের মাধ্যমে কথোপকথনে কনটেন্ট দিতে `--text -` ব্যবহার করুন:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
