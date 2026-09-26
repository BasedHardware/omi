# এজেণ্টসকলৰ বাবে omi-cli

> LLM-চালিত হাৰ্নেছসমূহৰ (Claude Code, Cursor, আপোনাৰ নিজৰ বট) বাবে ব্যৱহাৰিক গাইড।

## কিয় CLI এজেণ্ট-বান্ধৱী

* **স্থিৰ JSON চুক্তি।** `--json` এ stdout-লৈ এটা বৈধ JSON দস্তাবেজহে প্ৰেৰণ কৰে আৰু
  *কেৱল* এটা JSON দস্তাবেজ — কোনো প্ৰগ্ৰেছ বাৰ্তা নাই, কোনো স্পিনাৰ নাই। ত্ৰুটিসমূহ
  stderr-লৈ `{"error": "...", "detail": "..."}` ৰূপত যায়।
* **স্থিৰ exit ক'ড।** `0` সফল / `1` ব্যৱহাৰ / `2` প্ৰমাণীকৰণ / `3` চাৰ্ভাৰ /
  `4` হাৰ-সীমা / `5` বিচাৰি নোপোৱা। এজেণ্টসকলে প্ৰাকৃতিক-ভাষাৰ ত্ৰুটি বিশ্লেষণ
  নকৰাকৈয়ে এই ক'ডসমূহৰ ওপৰত শাখা কৰিব পাৰে।
* **হেডলেছ পৰিৱেশত কোনো ইন্টাৰেক্টিভ প্ৰম্পট নাই।** ধ্বংসাত্মক কমাণ্ডৰ বাবে
  `--yes` (বা `-y`) দিয়ক; ইন্টাৰেক্টিভ লগইন এৰাই চলিবলৈ `--api-key` দিয়ক বা
  `OMI_API_KEY` ছেট কৰক।
* **ক্ষমাশীল পুনৰ-চেষ্টা ব্যৱহাৰ।** `429` আৰু `5xx` ওলোৱাৰ আগতে
  বেকঅফসহ পুনৰ চেষ্টা কৰা হয়।

## প্ৰমাণীকৰণ (এবাৰমাত্ৰ, মানুহৰ দ্বাৰা)

ব্যৱহাৰকাৰীয়ে Omi ৱেব এপৰ (`https://app.omi.me` → Developer → API Keys) পৰা dev API
কী লয় আৰু তলৰ এটা বাট লয়:

```bash
omi auth login                          # ইন্টাৰেক্টিভ পেষ্ট; কী shell ইতিহাসত নাথাকে
# বা
export OMI_API_KEY=omi_dev_...          # অস্থায়ী, কণ্টেইনাৰ-বান্ধৱী
```

## এজেণ্টসকলে আটাইতকৈ বেছি কৰা পাঁচটা কাম

### 1. স্মৃতিসমূহ পঢ়ক

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. এটা স্মৃতি সৃষ্টি কৰক

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. কথোপকথনসমূহ পঢ়ক

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. খোলা কাৰ্য-বস্তুসমূহ পঢ়ক

```bash
omi action-item list --json --open
```

### 5. এটা কাৰ্য-বস্তু সম্পূৰ্ণ বুলি চিহ্নিত কৰক

```bash
omi action-item complete --json a1b2c3d4
```

## স্থানীয় Desktop API

যেতিয়া Omi Desktop এ নিজৰ স্থানীয় API উন্মোচন কৰে, এজেণ্টসকলে ক্লাউড dev API
ব্যৱহাৰ নকৰাকৈ ডিভাইচৰ স্ক্ৰীন ইতিহাস, পুনৰাৱলোকন, SQL আৰু টাস্কসমূহ অনুসন্ধান
কৰিব পাৰে:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# বা, অস্থায়ী ছেছনৰ বাবে:
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

কেৱল ব্যৱহাৰকাৰীয়ে স্পষ্টকৈ ক'লেহে টাস্কসমূহ সম্পূৰ্ণ বা মচি পেলাওক:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` এ স্ক্ৰীনশ্বট ডিস্কত লিখে আৰু
স্ক্ৰিপ্টৰ বাবে stdout-লৈ JSON প্ৰিন্ট কৰি থাকে। স্ক্ৰীনশ্বট ID সাধাৰণতে
`local search-screen` বা `screenshots` টেবুলৰ ওপৰত SQL ৰ পৰা আহে। যদি Desktop এ
`screenshot_pending`, `screenshot_file_missing` বা `screenshot_chunk_corrupted` ৰ দৰে
গাঁথনিগত বিফলতা ঘূৰাই দিয়ে, তেন্তে JSON ম'ডে stderr-ত `reason`, `hint` আৰু
`screenshot_id` ফীল্ডসমূহ সংৰক্ষণ কৰে, যাতে এজেণ্টসকলে পুৰণি ID ৰে পুনৰ চেষ্টা কৰিব
পাৰে বা সঠিক প্ৰতিবন্ধকতা ৰিপৰ্ট কৰিব পাৰে। সফল আউটপুটসমূহ vision সঁজুলিসমূহলৈ
প্ৰেৰণ কৰাৰ আগতে `file PATH` ৰে যাচাই কৰক।

## কৰা উদাহৰণ: Python এজেণ্ট লুপ

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """omi CLI ক JSON ম'ডত মাতক, অসফল exit ক'ডত exception তুলক।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI এ JSON ম'ডত stderr-লৈ গাঁথনিগত ত্ৰুটি প্ৰিন্ট কৰে:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# সকলো খোলা কাৰ্য-বস্তু পঢ়ক আৰু 30 দিনৰ পুৰণি সকলো সম্পূৰ্ণ বুলি চিহ্নিত কৰক।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## হাৰ-সীমাসমূহ পৰিচালনা কৰা

স্মৃতি: 120/ঘণ্টা। কথোপকথন: 25/ঘণ্টা। বেটচ সৃষ্টি: 15/ঘণ্টা।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # হাৰ-সীমিত
    err = json.loads(result.stderr)
    # err["detail"] এনেকুৱা দেখা যায়: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## টিপছ

* আপোনাৰ এজেণ্টে যদি একাধিক Omi একাউণ্ট চলায়, তেন্তে `--profile <name>`
  ব্যৱহাৰ কৰক। প্ৰতিটো প্ৰফাইলৰ নিজৰ প্ৰমাণপত্ৰ আৰু API বেছ থাকে।
* স্থানীয় বেকএণ্ড পৰীক্ষাৰ বাবে `--api-base http://localhost:8080` ব্যৱহাৰ কৰক।
* এটা ৰানৰ বাবে প্ৰফাইল-স্থানীয় Desktop API ছেটিংসমূহ ওভাৰৰাইড কৰিবলৈ
  `OMI_LOCAL_API_URL` আৰু `OMI_LOCAL_TOKEN` ব্যৱহাৰ কৰক।
* ডিবাগিংৰ বাবে `--verbose` ব্যৱহাৰ কৰক — ই stderr-ত `METHOD path → status (Ns)`
  লগ কৰে stdout-ত প্ৰভাৱ নেপেলায়, গতিকে JSON ম'ড বৈধ হৈ থাকে।
* কথোপকথনলৈ সমল পাইপ কৰিবলৈ `--text -` ব্যৱহাৰ কৰক:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
