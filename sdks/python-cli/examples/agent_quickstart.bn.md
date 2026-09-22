# এআই এজেন্টের জন্য omi-cli

> এলএলএম চালিত পরিবেশের জন্য ব্যবহারিক নির্দেশিকা (Claude Code, Cursor, কাস্টম বট)।

## কেন এই সিএলআই এজেন্ট-বান্ধব

* **স্থিতিশীল JSON চুক্তি:** `--json` ফ্ল্যাগটি stdout-এ সঠিক JSON নথিপত্র আউটপুট করে এবং *শুধুমাত্র* JSON — কোনো স্থিতি বার্তা বা লোডিং স্পিনার ছাড়া। ত্রুটিগুলি stderr-এ `{"error": "...", "detail": "..."}` বিন্যাসে পাঠানো হয়।
* **স্থিতিশীল এক্সিট কোড:** `0` সফল / `1` ব্যবহারজনিত ত্রুটি / `2` প্রমাণীকরণ ব্যর্থ / `3` সার্ভার ত্রুটি / `4` রেট লিমিট অতিক্রম / `5` পাওয়া যায়নি। কোনো প্রাকৃতিক ভাষা পার্সিং ছাড়াই এজেন্টরা সরাসরি এক্সিট কোড অনুযায়ী লজিক ভাগ করতে পারে।
* **হেডলেস মোডে কোনো ইন্টারঅ্যাক্টিভ প্রম্পট নেই:** ধ্বংসাত্মক কমান্ডের জন্য `--yes` (বা `-y`) পাস করুন; ব্রাউজার লগইন এড়াতে `--api-key` দিন বা `OMI_API_KEY` সেট করুন।
* **স্বয়ংক্রিয় পুনঃচেষ্টা আচরণ:** ত্রুটি ফেরত দেওয়ার আগে `429` এবং `5xx` প্রতিক্রিয়াগুলি সূচকীয় বিলম্বের সাথে স্বয়ংক্রিয়ভাবে পুনঃচেষ্টা করা হয়।

## প্রমাণীকরণ (ব্যবহারকারী দ্বারা একবার)

ব্যবহারকারী Omi ওয়েব অ্যাপ থেকে ডেভেলপার API কী পান
(`https://app.omi.me` → Developer → API Keys), তারপর চালান:

```bash
omi auth login                          # পেস্ট করুন; শেল ইতিহাসে সংরক্ষিত হয় না
# অথবা
export OMI_API_KEY=omi_dev_...          # অস্থায়ী, কন্টেইনার এবং CI/CD এর জন্য উপযুক্ত
```

## এজেন্টের পাঁচটি সর্বাধিক সাধারণ অপারেশন

### ১. স্মৃতিসমূহ পড়া (Memories)

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### ২. স্মৃতি তৈরি করা

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### ৩. কথোপকথন পড়া

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ৪. করণীয় কাজসমূহ পড়া (Action Items)

```bash
omi action-item list --json --open
```

### ৫. কাজ সম্পন্ন হিসেবে চিহ্নিত করা

```bash
omi action-item complete --json a1b2c3d4
```

## লোকাল ডেস্কটপ API (Local Desktop API)

যখন Omi Desktop স্থানীয় API সক্রিয় করে, তখন এজেন্টরা ক্লাউড ডেভ API কল না করেই স্ক্রিন ইতিহাস, সারাংশ এবং SQL অনুসন্ধান করতে পারে:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# অথবা অস্থায়ী সেশনের জন্য:
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

শুধুমাত্র যখন ব্যবহারকারী স্পষ্টভাবে অনুরোধ করেন তখন কাজ সম্পন্ন বা মুছে ফেলুন:

শুধুমাত্র ব্যবহারকারী স্পষ্টভাবে অনুরোধ করলেই কাজগুলো সম্পন্ন বা মুছে ফেলুন:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` কমান্ডটি স্ক্রিনশট ডিস্কে সংরক্ষণ করে এবং স্ক্রিপ্টের জন্য stdout-এ JSON আউটপুট প্রদান করে। স্ক্রিনশট আইডি সাধারণত `local search-screen` বা `screenshots` টেবিলের উপর SQL কোয়েরি থেকে পাওয়া যায়। যদি Desktop কোনো কাঠামোগত ত্রুটি যেমন `screenshot_pending`, `screenshot_file_missing` বা `screenshot_chunk_corrupted` প্রদান করে, তবে JSON মোড stderr-এ `reason`, `hint` এবং `screenshot_id` ফিল্ড সংরক্ষণ করে যাতে এজেন্টরা পুরোনো কোনো আইডি দিয়ে পুনরায় চেষ্টা করতে পারে বা সঠিক সমস্যা রিপোর্ট করতে পারে। ভিশন টুলে পাঠানোর পূর্বে `file PATH` ব্যবহার করে সফল আউটপুট যাচাই করে নিন।

## কার্যকরী উদাহরণ: পাইথন (Python) এজেন্ট লুপ

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

## রেট লিমিট হ্যান্ডলিং (Handling rate limits)

স্মৃতি (Memories): ১২০/ঘণ্টা। কথোপকথন (Conversations): ২৫/ঘণ্টা। ব্যাচ তৈরি (Batch creates): ১৫/ঘণ্টা।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## গুরুত্বপূর্ণ টিপস (Tips)

* একাধিক Omi অ্যাকাউন্ট পরিচালনার ক্ষেত্রে `--profile <name>` ব্যবহার করুন। প্রতিটি প্রোফাইলের নিজস্ব ক্রেডেনশিয়াল এবং API বেস থাকে।
* লোকাল ব্যাকএন্ড পরীক্ষার জন্য `--api-base http://localhost:8080` ব্যবহার করুন।
* এককালীন ডেস্কটপ API কনফিগারেশন প্রতিস্থাপনের জন্য `OMI_LOCAL_API_URL` এবং `OMI_LOCAL_TOKEN` ব্যবহার করুন।
* ডিবাগিংয়ের জন্য `--verbose` ব্যবহার করুন — এটি stdout প্রভাবিত না করে stderr-এ `METHOD path → status (Ns)` লগ করে, ফলে JSON আউটপুট অক্ষত থাকে।
* কোনো কথোপকথনে সরাসরি পাইপিংয়ের মাধ্যমে টেক্সট ইনপুট দিতে `--text -` ব্যবহার করুন:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
