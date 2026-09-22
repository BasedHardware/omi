# omi-cli აგენტებისთვის (agents)

> პრაქტიკული სახელმძღვანელო LLM-ით მართული სისტემებისთვის (Claude Code, Cursor, თქვენი პირადი ბოტები).

## რატომ არის CLI აგენტებისთვის მოსახერხებელი

* **სტაბილური JSON კონტრაქტი.** `--json` დროშა stdout-ში გამოიტანს ვალიდურ JSON დოკუმენტს
  და *მხოლოდ* JSON დოკუმენტს — ყოველგვარი პროგრესის შეტყობინებების ან სპინერების გარეშე.
  შეცდომები იგზავნება stderr-ში სახით `{"error": "...", "detail": "..."}`.
* **სტაბილური გამოსვლის კოდები (Exit Codes).** `0` წარმატება / `1` გამოყენება / `2` ავთენტიფიკაცია / `3` სერვერი / `4` მოთხოვნათა
  ლიმიტი / `5` ვერ მოიძებნა. აგენტებს შეუძლიათ განშტოება ამ კოდების მიხედვით ბუნებრივი
  ენის შეცდომების პარსინგის გარეშე.
* **ინტერაქტიული შეკითხვების გარეშე headless გარემოში.** გადაეცით `--yes` (ან `-y`)
  დესტრუქციულ ბრძანებებს; გადაეცით `--api-key` ან განსაზღვრეთ `OMI_API_KEY` ინტერაქტიული შესვლის
  გამოსატოვებლად.
* **მომტევებელი განმეორებითი ცდის ქცევა.** `429` და `5xx` შეცდომები ავტომატურად მეორდება
  ექსპონენციალური დაყოვნებით, სანამ შეცდომად დაფიქსირდება.

## ავთენტიფიკაცია (ერთხელ, ადამიანის მიერ)

მომხმარებელი იღებს დეველოპერის API გასაღებს Omi ვებ-აპლიკაციიდან
(`https://app.omi.me` → Developer → API Keys) და ასრულებს ერთ-ერთს:

```bash
omi auth login                          # ინტერაქტიული ჩასმა; გასაღები არ რჩება ისტორიაში
# ან
export OMI_API_KEY=omi_dev_...          # დროებითი, მოსახერხებელი კონტეინერებისთვის
```

## ხუთი მოქმედება, რასაც აგენტები ყველაზე ხშირად ასრულებენ

### 1. მოგონებების წაკითხვა

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. მოგონების შექმნა

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. საუბრების წაკითხვა

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. ღია დავალებების წაკითხვა

```bash
omi action-item list --json --open
```

### 5. დავალების შესრულებულად მონიშვნა

```bash
omi action-item complete --json a1b2c3d4
```

## ლოკალური Desktop API

როდესაც Omi Desktop ხელმისაწვდომს ხდის თავის ლოკალურ API-ს, აგენტებს შეუძლიათ მოითხოვონ
ეკრანის ისტორია მოწყობილობაზე, შეჯამებები, SQL და დავალებები ღრუბლოვანი API-ს გარეშე:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ან, დროებითი სესიებისთვის:
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

შეასრულეთ ან წაშალეთ დავალებები მხოლოდ მაშინ, როცა მომხმარებელი მკაფიოდ ითხოვს:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ბრძანება წერს სქრინშოტს დისკზე
და მაინც ბეჭდავს JSON-ს stdout-ში სკრიპტებისთვის. სქრინშოტის ID ჩვეულებრივ
მოდის `local search-screen`-დან ან `screenshots` ცხრილის SQL მოთხოვნიდან. თუ Desktop
აბრუნებს სტრუქტურირებულ შეცდომას, როგორიცაა `screenshot_pending`, `screenshot_file_missing`
ან `screenshot_chunk_corrupted`, JSON რეჟიმი ინახავს `reason`, `hint` და
`screenshot_id` ველებს stderr-ში, რათა აგენტებმა შეძლონ ძველი ID-ს ხელახლა ცდა
ან ზუსტი დაბრკოლების შეტყობინება. გადაამოწმეთ წარმატებული გამონატანი `file PATH` ბრძანებით
ვიზუალურ ხელსაწყოებთან გადაცემამდე.

## პრაქტიკული მაგალითი: Python აგენტის ციკლი

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """გამოიძახეთ omi CLI JSON რეჟიმში, შეცდომის აღძვრით არაწარმატებულ გამოსვლის კოდებზე."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ბეჭდავს სტრუქტურირებულ შეცდომებს stderr-ში JSON რეჟიმში:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# წაიკითხეთ ყველა ღია დავალება და მონიშნეთ შესრულებულად 30 დღეზე ძველი ნებისმიერი ერთეული.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## მოთხოვნათა ლიმიტების (Rate limits) მართვა

მოგონებები: 120/საათში. საუბრები: 25/საათში. ჯგუფური შექმნა: 15/საათში.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # მოთხოვნათა ლიმიტი ამოიწურა
    err = json.loads(result.stderr)
    # err["detail"] გამოიყურება ასე: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## რჩევები

* გამოიყენეთ `--profile <სახელი>`, თუ თქვენი აგენტი მართავს რამდენიმე Omi ანგარიშს.
  თითოეულ პროფილს აქვს თავისი სერთიფიკატი და API ბაზა.
* გამოიყენეთ `--api-base http://localhost:8080` ლოკალური ბექენდის ტესტირებისთვის.
* გამოიყენეთ `OMI_LOCAL_API_URL` და `OMI_LOCAL_TOKEN` ერთი გაშვებისთვის ლოკალური
  Desktop API-ს პარამეტრების გადასაწერად.
* გამოიყენეთ `--verbose` გამართვისთვის — ის აღრიცხავს `METHOD path → status (Ns)`
  stderr-ში stdout-ზე ზემოქმედების გარეშე, ასე რომ JSON რეჟიმი რჩება ვალიდური.
* საუბარში შინაარსის გადასაცემად (pipe), გამოიყენეთ `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
