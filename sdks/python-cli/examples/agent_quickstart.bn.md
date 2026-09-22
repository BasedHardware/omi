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

```bash
omi --json local task complete task_1
```
