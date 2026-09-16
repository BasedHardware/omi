# omi-cli দ্রুত শুরুর নির্দেশিকা (Bengali Quickstart)

> টার্মিনাল থেকে সরাসরি Omi ব্যবহারের একটি ব্যবহারিক নির্দেশিকা, যা সফটওয়্যার ডেভেলপার এবং স্বায়ত্তশাসিত AI এজেন্টদের জন্য তৈরি করা হয়েছে।

`omi-cli` হলো [Omi](https://omi.me) ডেভেলপার API-এর অফিসিয়াল কমান্ড-লাইন ইন্টারফেস (CLI)। এটি Omi-এর ৪টি মূল রিসোর্সে কাঠামোগত অ্যাক্সেস সরবরাহ করে: স্মৃতি (memories), কথোপকথন (conversations), করণীয় কাজ (action items), এবং লক্ষ্য (goals)।

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **অফিসিয়াল ডকুমেন্টেশন:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **সোর্স কোড:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## ১. ইনস্টলেশন

সিস্টেমের প্যাকেজ দ্বন্দ্ব এড়াতে এবং একটি পরিষ্কার বিচ্ছিন্ন পরিবেশ নিশ্চিত করতে `pipx` ব্যবহার করার জোরালো সুপারিশ করা হয়:

```bash
# প্রস্তাবিত পদ্ধতি: pipx-এর মাধ্যমে বিচ্ছিন্ন ইনস্টলেশন
pipx install omi-cli

# বিকল্প পদ্ধতি: স্ট্যান্ডার্ড pip-এর মাধ্যমে ইনস্টলেশন (যেমন virtualenv-এ)
pip install omi-cli
```

> **গুরুত্বপূর্ণ স্পষ্টীকরণ: প্যাকেজের নাম বনাম কমান্ডের নাম**
> * PyPI-তে প্যাকেজের অফিসিয়াল নাম হলো **`omi-cli`** (শুধুমাত্র `omi` নামের প্যাকেজটি একটি ভিন্ন এবং সম্পর্কহীন প্রজেক্ট)।
> * টার্মিনালে চালানোর জন্য কমান্ডটি সরাসরি: **`omi`**।

ইনস্টলেশন সফল হয়েছে কিনা তা নিশ্চিত করতে সংস্করণ এবং সহায়তা মেনু পরীক্ষা করুন:

```bash
omi --version
omi --help
```

---

## ২. প্রমাণীকরণ (Authentication)

`omi-cli` দুটি প্রাথমিক প্রমাণীকরণ পদ্ধতি সমর্থন করে:

| পদ্ধতি | উদ্দেশ্য | কমান্ডের উদাহরণ |
| :--- | :--- | :--- |
| **ডেভেলপার API কী (`omi_dev_*`)** | অটোমেশন, CI/CD পাইপলাইন, হেডলেস সার্ভার, AI এজেন্ট | `omi auth login --api-key ...` অথবা `OMI_API_KEY` |
| **ব্রাউজার OAuth লগইন (Google/Apple)** | ব্যক্তিগত কম্পিউটারে স্থানীয় ডেভেলপমেন্ট | `omi auth login --browser` (Google) / `--provider apple` |

### ইন্টারেক্টিভ লগইন
কোনো অতিরিক্ত প্যারামিটার ছাড়া কমান্ডটি চালালে একটি ইন্টারেক্টিভ মেনু খোলে:

```bash
omi auth login
# 1) Browser: ব্রাউজারের মাধ্যমে Google দিয়ে সাইন ইন (Apple-এর জন্য `--provider apple` ব্যবহার করুন)
# 2) API key: app.omi.me থেকে প্রাপ্ত ডেভেলপার API কী পেস্ট করুন
```

### ব্রাউজারের মাধ্যমে সরাসরি লগইন
```bash
# স্ট্যান্ডার্ড Google অ্যাকাউন্ট দিয়ে লগইন
omi auth login --browser

# Apple আইডি ব্যবহার করে বিকল্প লগইন
omi auth login --browser --provider apple
```

### ডেভেলপার API কী দিয়ে লগইন
[app.omi.me](https://app.omi.me) ড্যাশবোর্ডের **Developer -> API Keys** বিভাগ থেকে একটি API কী তৈরি করুন:

```bash
# স্থানীয় প্রোফাইলে কী সংরক্ষণ করুন
omi auth login --api-key omi_dev_...

# অথবা এনভায়রনমেন্ট ভেরিয়েবল হিসেবে সেট করুন (Docker এবং CI/CD-এর জন্য আদর্শ):
# দ্রষ্টব্য: প্রোফাইলে আগে থেকেই কোনো সংরক্ষিত কী থাকলে প্রথমে `omi auth logout` চালান।
export OMI_API_KEY="omi_dev_আপনার_কী_এখানে"
```

### প্রমাণীকরণ অবস্থা যাচাইকরণ
* `omi auth status`: কোনো নেটওয়ার্ক অনুরোধ ছাড়াই সক্রিয় প্রোফাইল এবং মাস্ক করা ক্রেডেনশিয়াল দেখায় (অফলাইনে কাজ করে)।
* `omi auth whoami`: সেশনের বৈধতা নিশ্চিত করতে Omi সার্ভারে অনুরোধ পাঠায় (ইন্টারনেট সংযোগ প্রয়োজন)।

```bash
omi auth status
omi auth whoami
```

### লগআউট (Logout)
```bash
omi auth logout
# আপনি যদি OMI_API_KEY এনভায়রনমেন্ট ভেরিয়েবল ব্যবহার করে থাকেন, তবে তা সেশন থেকে সরিয়ে ফেলুন (Bash/Zsh: `unset OMI_API_KEY`)।
```

---

## ৩. মূল কমান্ডসমূহ

### স্মৃতি (Memories)
Omi দ্বারা সংরক্ষিত প্রাসঙ্গিক নোট এবং পর্যবেক্ষণ:

```bash
# সংরক্ষিত স্মৃতির তালিকা দেখুন
omi memory list

# নতুন স্মৃতি তৈরি করুন
omi memory create "পাইথন উদাহরণের সাথে সংক্ষিপ্ত এবং প্রযুক্তিগত উত্তর পছন্দ করেন" --category work

# আইডি দিয়ে নির্দিষ্ট স্মৃতি দেখুন
omi memory get <MEMORY_ID>
```

### কথোপকথন (Conversations)
Omi ডিভাইস থেকে রেকর্ড করা কথোপকথন এবং প্রতিলিপি:

```bash
# সাম্প্রতিক ৫টি কথোপকথনের তালিকা দেখুন
omi conversation list --limit 5

# সম্পূর্ণ প্রতিলিপিসহ কথোপকথন দেখুন
omi conversation get <CONVERSATION_ID> --include-transcript
```

### করণীয় কাজ (Action Items)
কথোপকথন থেকে স্বয়ংক্রিয়ভাবে সনাক্ত করা কাজ:

```bash
# চলমান/উন্মুক্ত কাজের তালিকা দেখুন
omi action-item list --open

# কাজ সম্পন্ন হিসেবে চিহ্নিত করুন
omi action-item complete <ACTION_ITEM_ID>
```

### লক্ষ্য (Goals)
দীর্ঘমেয়াদী লক্ষ্য এবং অগ্রগতি ট্র্যাকিং:

```bash
# সক্রিয় লক্ষ্যগুলির তালিকা দেখুন
omi goal list

# সংখ্যাসূচক পরিমাপযোগ্য লক্ষ্য তৈরি করুন
omi goal create "প্রতিদিন ২ লিটার পানি পান করুন" --type numeric --target 2 --unit liters
```

---

## ৪. কাঠামোগত অটোমেশন এবং JSON আউটপুট (`--json`)

`omi-cli` স্ক্রিপ্ট ইন্টিগ্রেশন এবং AI এজেন্টদের ব্যবহারের জন্য অপ্টিমাইজ করা হয়েছে। গ্লোবাল `--json` ফ্ল্যাগটি বৈধ JSON প্রদান করে যা `jq`-এর মতো টুল দিয়ে প্রক্রিয়া করা যায়:

```bash
# JSON ফরম্যাটে স্মৃতির তালিকা এবং jq দিয়ে ফিল্টারিং
omi --json memory list | jq '.[] | {id, content, category}'

# সাম্প্রতিক কথোপকথনের শিরোনাম সংগ্রহ করুন
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# উন্মুক্ত কাজগুলির কাঁচা JSON আউটপুট দেখুন
omi --json action-item list --open | jq '.'
```

> **সিনট্যাক্সের গুরুত্বপূর্ণ নিয়ম:**
> `--json` ফ্ল্যাগটি একটি **গ্লোবাল অপশন**, অর্থাৎ এটিকে সাব-কমান্ড ক্রিয়াপদের **আগে** রাখতে হবে:
> * সঠিক: `omi --json memory list`
> * ভুল: `omi memory list --json`

### পেজিনেশন এবং ফাইলে এক্সপোর্ট
বিপুল পরিমাণ ডেটা প্রক্রিয়াকরণের জন্য `--limit` এবং `--offset` প্যারামিটার ব্যবহার করুন:

```bash
# পেজিনেশন সহ ফলাফল সংরক্ষণ করুন
omi --json memory list --limit 25 --offset 0 > smriti-page-1.json
omi --json memory list --limit 25 --offset 25 > smriti-page-2.json
```

---

## ৫. এক্সিট কোড (Exit Codes)

স্ক্রিপ্ট এবং CI/CD পাইপলাইনে নির্ভরযোগ্য ত্রুটি ব্যবস্থাপনার জন্য এক্সিট কোডসমূহ:

| কোড | কোডের নাম | বিবরণ |
| :---: | :--- | :--- |
| `0` | **`EXIT_OK`** | কোনো ত্রুটি ছাড়াই কমান্ডটি সফলভাবে সম্পন্ন হয়েছে। |
| `1` | **`EXIT_USAGE`** | ভুল ব্যবহার, ভুল সিনট্যাক্স বা অনুপস্থিত আর্গুমেন্ট। |
| `2` | **`EXIT_AUTH`** | প্রমাণীকরণ ব্যর্থতা, মেয়াদোত্তীর্ণ কী বা অনুমতির অভাব। |
| `3` | **`EXIT_SERVER`** | সার্ভার ত্রুটি (HTTP 5xx), নেটওয়ার্ক সমস্যা বা টাইমআউট। |
| `4` | **`EXIT_RATE_LIMITED`** | অনুরোধের সীমা অতিক্রম করেছে (HTTP 429)। |
| `5` | **`EXIT_NOT_FOUND`** | অনুরোধ করা রিসোর্স সার্ভারে খুঁজে পাওয়া যায়নি (HTTP 404)। |

---

## ৬. বিভিন্ন টার্মিনাল পরিবেশের উদাহরণ

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_আপনার_কী_এখানে"

# কমান্ড চালানো এবং এক্সিট কোড পরীক্ষা করা
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "স্মৃতি সংগ্রহ করতে একটি ত্রুটি ঘটেছে।" >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_আপনার_কী_এখানে"

# JSON আউটপুটকে সরাসরি PowerShell অবজেক্টে রূপান্তর
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# $LASTEXITCODE দিয়ে ত্রুটি পরীক্ষা
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi কমান্ড ব্যর্থ হয়েছে, ত্রুটি কোড: $LASTEXITCODE."
}
```

---

## ৭. লোকাল ডেস্কটপ API ইন্টিগ্রেশন (Local Desktop API)

Omi ডেস্কটপ অ্যাপ্লিকেশন একই কম্পিউটারে চলমান থাকলে ক্লাউড ছাড়াই স্থানীয় স্ক্রিন ডেটা অনুসন্ধান করা যায়:

```bash
# স্থানীয় ঠিকানা এবং টোকেন সেট করুন
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "ডেস্কটপ টোকেন দিন: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# স্থানীয় সার্ভিসের অবস্থা যাচাই করুন
omi --json local status

# স্থানীয় স্ক্রিন রেকর্ডে অনুসন্ধান করুন
omi --json local search-screen "ত্রৈমাসিক রিপোর্ট" --days 7 --app Safari
```

---

## ৮. একাধিক প্রোফাইল ব্যবস্থাপনা (Profiles)

`--profile` ফ্ল্যাগ ব্যক্তিগত, প্রাতিষ্ঠানিক বা স্টেজিং অ্যাকাউন্ট আলাদা রাখতে সাহায্য করে। কনফিগারেশন `~/.omi/config.toml` ফাইলে সংরক্ষিত থাকে:

```bash
# ব্যক্তিগত প্রোফাইলে সাইন ইন
omi --profile personal auth login

# প্রাতিষ্ঠানিক কাজের প্রোফাইলে সাইন ইন
omi --profile work auth login

# নির্দিষ্ট প্রোফাইল দিয়ে কমান্ড চালানো
omi --profile work memory list

# স্টেজিং টেস্ট এনভায়রনমেন্ট ব্যবহার
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## ৯. নিরাপত্তা এবং সর্বোত্তম অনুশীলন

* **Git-এ কী শেয়ার করবেন না:** কখনোই পাবলিক গিট রিপোজিটরিতে API কী কমিট করবেন না। `.gitignore`-এ তালিকাভুক্ত এনভায়রনমেন্ট ফাইল ব্যবহার করুন।
* **টার্মিনাল ইতিহাস সুরক্ষিত রাখুন:** শেয়ার্ড কম্পিউটারে কমান্ড লাইনে সংবেদনশীল কী টাইপ করা এড়িয়ে চলুন; ইন্টারেক্টিভ লগইন বা `OMI_API_KEY` ব্যবহার করুন।
* **ফাইল অনুমতি:** ইউনিক্স সিস্টেমে `~/.omi/` ডিরেক্টরির জন্য কঠোর ফাইল অনুমতি সেট করুন (`chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`)।
