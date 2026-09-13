# omi-cli কুইক স্টার্ট গাইড (Bengali Quickstart)

> টার্মিনাল থেকে সরাসরি Omi-এর সাথে ইন্টারঅ্যাক্ট করার ব্যবহারিক নির্দেশিকা — ডেভেলপার ও স্বায়ত্তশাসিত AI এজেন্টদের জন্য তৈরি।

`omi-cli` হলো [Omi](https://omi.me) ডেভেলপার API-এর অফিসিয়াল কমান্ড-লাইন ইন্টারফেস। এটি দিয়ে সিস্টেমের ৪টি মূল রিসোর্স — মেমরি (memories), কথোপকথন (conversations), অ্যাকশন আইটেম (action items) এবং লক্ষ্য (goals) — গঠনসহ পরিচালনা ও অটোমেট করা যায়।

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **অফিসিয়াল ডকুমেন্টেশন:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **সোর্স কোড:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## ১. ইনস্টলেশন

সিস্টেমের ডিপেন্ডেন্সি দ্বন্দ্ব এড়াতে এবং CLI টুলটি আলাদা পরিবেশে চালাতে `pipx` ব্যবহার করার পরামর্শ দেওয়া হয়:

```bash
# প্রস্তাবিত: pipx দিয়ে আইসোলেটেড ইনস্টল
pipx install omi-cli

# বিকল্প: সাধারণ pip ইনস্টল
pip install omi-cli
```

> **সতর্কতা: প্যাকেজের নাম বনাম কমান্ডের নাম**
> * PyPI-তে প্যাকেজের নাম **`omi-cli`** (`omi` নামের প্যাকেজটি সম্পর্কহীন অন্য প্যাকেজ)।
> * টার্মিনালে চালানোর কমান্ডটি হলো **`omi`**।

ইনস্টলেশন সফল হয়েছে কিনা ভার্সন ও হেল্প মেনু দিয়ে যাচাই করুন:

```bash
omi --version
omi --help
```

---

## ২. প্রমাণীকরণ (Authentication)

`omi-cli` দুটি প্রধান প্রমাণীকরণ পদ্ধতি সমর্থন করে:

| পদ্ধতি | ব্যবহারক্ষেত্র | উদাহরণ কমান্ড |
| :--- | :--- | :--- |
| **ডেভেলপার API কী (`omi_dev_*`)** | অটোমেশন, CI/CD, হেডলেস সার্ভার, AI এজেন্ট | `omi auth login --api-key ...` অথবা `OMI_API_KEY` |
| **ব্রাউজার OAuth (Google/Apple)** | লোকাল ওয়ার্কস্টেশন ও ডেভেলপার | `omi auth login --browser` (Google) / `--provider apple` |

### ইন্টারঅ্যাক্টিভ লগইন
কোনো অপশন ছাড়া চালালে পদ্ধতি বাছাইয়ের মেনু দেখাবে:

```bash
omi auth login
# 1) Browser — ব্রাউজার দিয়ে Google লগইন (Apple অ্যাকাউন্টের জন্য `--provider apple`)
# 2) API key — app.omi.me থেকে তৈরি API কী পেস্ট করুন
```

### ব্রাউজার দিয়ে সরাসরি লগইন
```bash
# ডিফল্ট Google লগইন
omi auth login --browser

# বিকল্প: Apple অ্যাকাউন্ট লগইন
omi auth login --browser --provider apple
```

### ডেভেলপার API কী ব্যবহার
আপনার কী [app.omi.me](https://app.omi.me) প্যানেলের **Developer → API Keys** অংশ থেকে তৈরি করুন:

```bash
# কমান্ড দিয়ে লোকাল প্রোফাইলে সংরক্ষণ
omi auth login --api-key omi_dev_...

# অথবা এনভায়রনমেন্ট ভ্যারিয়েবল হিসেবে সেট করুন (কনটেইনার ও CI/CD-র জন্য সেরা)
# নোট: সক্রিয় লোকাল প্রোফাইলে কী সংরক্ষিত থাকলে আগে `omi auth logout` চালান।
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### প্রমাণীকরণের অবস্থা যাচাই
* `omi auth status`: সক্রিয় লোকাল প্রোফাইল ও মাস্ক করা ক্রেডেনশিয়াল দেখায়; মেয়াদোত্তীর্ণের তারিখ শুধু OAuth প্রোফাইলের জন্য দেখানো হয় (অফলাইনে কাজ করে)।
* `omi auth whoami`: পরিচয়ের লাইভ সার্ভার যাচাইয়ের জন্য Omi API-তে রিকোয়েস্ট পাঠায় (নেটওয়ার্ক প্রয়োজন)।

```bash
omi auth status
omi auth whoami
```

লগআউট:
```bash
omi auth logout
# এনভায়রনমেন্টে OMI_API_KEY সেট থাকলে সেখান থেকেও সরান (Bash/Zsh: `unset OMI_API_KEY`)।
```

---

## ৩. মূল কমান্ডসমূহ

### মেমরি (Memories)
Omi সংরক্ষিত অ্যাটমিক প্রসঙ্গ-তথ্য:

```bash
# সংরক্ষিত মেমরির তালিকা
omi memory list

# নতুন মেমরি তৈরি
omi memory create "কারিগরি ও সংক্ষিপ্ত উত্তর পছন্দ করি, পাইথন উদাহরণসহ" --category work

# নির্দিষ্ট মেমরির বিস্তারিত
omi memory get <MEMORY_ID>
```

### কথোপকথন (Conversations)
Omi ডিভাইসে রেকর্ড হওয়া ভয়েস ট্রান্সক্রিপ্ট ও কথোপকথনের ইতিহাস:

```bash
# সর্বশেষ ৫টি কথোপকথনের তালিকা
omi conversation list --limit 5

# বিস্তারিত ও সম্পূর্ণ ট্রান্সক্রিপ্ট
omi conversation get <CONVERSATION_ID> --include-transcript
```

### অ্যাকশন আইটেম (Action Items)
কথোপকথন থেকে স্বয়ংক্রিয়ভাবে বের করা কাজের তালিকা:

```bash
# খোলা কাজগুলোর তালিকা
omi action-item list --open

# একটি কাজ সম্পন্ন করা
omi action-item complete <ACTION_ITEM_ID>
```

### লক্ষ্য (Goals)
অগ্রগতির মেট্রিক ও দীর্ঘমেয়াদি লক্ষ্য:

```bash
# সক্রিয় লক্ষ্যের তালিকা
omi goal list

# নতুন সংখ্যাভিত্তিক লক্ষ্য তৈরি
omi goal create "দিনে ২ লিটার পানি পান কর" --type numeric --target 2 --unit liters
```

---

## ৪. কাঠামোবদ্ধ অটোমেশন ও JSON আউটপুট (`--json`)

`omi-cli` অটোমেশন পাইপলাইনের জন্য প্রথম-শ্রেণির সমর্থন দেয়। গ্লোবাল `--json` ফ্ল্যাগ যোগ করলে আউটপুট বৈধ JSON-এ ফেরত আসে:

```bash
# মেমরি JSON আকারে তালিকা করে jq দিয়ে ফিল্ড বের করা
omi --json memory list | jq '.[] | {id, content, category}'

# সর্বশেষ কথোপকথনের শিরোনাম বের করা
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# খোলা অ্যাকশন আইটেম কাঁচা JSON হিসেবে দেখা
omi --json action-item list --open | jq '.'
```

> **গুরুত্বপূর্ণ সিনট্যাক্স নিয়ম:**
> `--json` ফ্ল্যাগটি **গ্লোবাল অপশন** — সাবকমান্ডের **আগে** বসতে হবে:
> * সঠিক: `omi --json memory list`
> * ভুল: `omi memory list --json`

---

## ৫. এক্সিট কোড (Exit Codes)

শেল স্ক্রিপ্ট ও CI/CD ওয়ার্কফ্লোতে নির্ভরযোগ্য ত্রুটি পরীক্ষা:

| এক্সিট কোড | অর্থ | বর্ণনা |
| :---: | :--- | :--- |
| `0` | **সফল (Success)** | কোনো ত্রুটি ছাড়াই কাজ সম্পন্ন। |
| `1` | **ব্যবহার-ত্রুটি (Validation)** | অবৈধ ডেটা মান বা অ্যাপ ভ্যালিডেশন ত্রুটি; Click পার্সারের সিনট্যাক্স ত্রুটিতে কোড `2` ফেরত দেয়। |
| `2` | **প্রমাণীকরণ / CLI সিনট্যাক্স ত্রুটি** | অপ্রমাণিত, মেয়াদোত্তীর্ণ টোকেন বা অজানা Click অপশন। |
| `3` | **সার্ভার / নেটওয়ার্ক ত্রুটি** | HTTP 5xx রেসপন্স, টাইমআউট বা সার্ভারে পৌঁছানো যাচ্ছে না। |
| `4` | **রেট লিমিট** | HTTP 429 রেসপন্স — হার-সীমার কারণে রিকোয়েস্ট ব্লক। |
| `5` | **পাওয়া যায়নি (Not Found)** | HTTP 404 রেসপন্স — অনুরোধকৃত রিসোর্স নেই। |

---

## ৬. শেল পরিবেশভেদে উদাহরণ

### Bash / Zsh (Linux / macOS)
```bash
# সেশনে API কী সেট করুন
export OMI_API_KEY="omi_dev_your_actual_key_here"

# কমান্ড চালিয়ে এক্সিট কোড যাচাই করুন
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "মেমরি কোয়েরি করার সময় ত্রুটি হয়েছে।" >&2
fi
```

### PowerShell (Windows)
```powershell
# PowerShell এনভায়রনমেন্ট ভ্যারিয়েবল সেট করুন
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# JSON আউটপুট সরাসরি PowerShell অবজেক্টে রূপান্তর
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE দিয়ে ত্রুটি পরীক্ষা
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi কমান্ড $LASTEXITCODE কোডে ব্যর্থ হয়েছে।"
}
```

---

## ৭. লোকাল ডেস্কটপ API ইন্টিগ্রেশন

Omi Desktop অ্যাপ কম্পিউটারে চালু থাকলে ক্লাউডে না গিয়ে লোকাল স্ক্রিন ও প্রসঙ্গ-ইতিহাস কোয়েরি করা যায়:

```bash
# লোকাল এন্ডপয়েন্ট কনফিগার করুন (টোকেন সুরক্ষার জন্য এনভায়রনমেন্ট ভ্যারিয়েবল ব্যবহার করুন)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# লোকাল সংযোগের অবস্থা যাচাই
omi --json local status

# সাম্প্রতিক ভিজ্যুয়াল টাইমলাইনে সার্চ
omi --json local search-screen "কোয়ার্টার রিপোর্ট" --days 7 --app Safari
```

---

## ৮. মাল্টি-প্রোফাইল ব্যবস্থাপনা (Profiles)

ব্যক্তিগত ও কাজের অ্যাকাউন্ট বা টেস্ট এনভায়রনমেন্টের মধ্যে সুইচ করতে `--profile` অপশন ব্যবহার করুন। সেটিংস `~/.omi/config.toml` ফাইলে থাকে:

```bash
# ব্যক্তিগত প্রোফাইল তৈরি করে লগইন
omi --profile personal auth login

# কাজের প্রোফাইল তৈরি করে লগইন
omi --profile work auth login

# নির্দিষ্ট প্রোফাইল দিয়ে কমান্ড চালানো
omi --profile work memory list

# কাস্টম টেস্ট এন্ডপয়েন্টসহ প্রোফাইল চালানো
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## ৯. নিরাপত্তা ও সেরা অনুশীলন

* **Git রিপোতে কী পাঠাবেন না:** API কী কখনো পাবলিক রিপোতে সংরক্ষণ করবেন না; সিক্রেট ম্যানেজার বা `.gitignore`-আচ্ছাদিত `.env` ফাইল ব্যবহার করুন।
* **শেল হিস্ট্রি:** শেয়ার্ড মেশিনে কী সরাসরি কমান্ড-লাইন আর্গুমেন্ট হিসেবে দেবেন না; ইন্টারঅ্যাক্টিভ ইনপুট বা `OMI_API_KEY` এনভায়রনমেন্ট ভ্যারিয়েবল ব্যবহার করুন।
* **ফোল্ডার পারমিশন:** Unix সিস্টেমে `~/.omi/` কনফিগ ডিরেক্টরির পারমিশন সীমাবদ্ধ করুন (`chmod 700 ~/.omi`)।
