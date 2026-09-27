# omi-cli بۆ بریکارەکان

> ڕێبەری پراکتیکی بۆ هارنێسەکانی بەڕێوەبردنی LLM (Claude Code، Cursor، بۆتەکانی خۆت).

## بۆچی CLI کە دۆستی بریکارە

* **گرێبەستی JSON ی جێگیر.** `--json` دۆکیومێنتێکی JSON ی دروست دەداتە stdout و *تەنها* دۆکیومێنتی JSON — بێ نامەی پێشکەوتن، بێ سپینەر. هەڵەکان دەچنە stderr وەک `{"error": "...", "detail": "..."}`.
* **کۆدەکانی دەرچوونی جێگیر.** `0` باشە / `1` بەکارهێنان / `2` ڕەسەنایەتی / `3` سێرڤەر / `4` سنووری ڕێژە / `5` نەدۆزرایەوە. بریکارەکان دەتوانن لەسەر ئەمانە لق بکەنەوە بەبێ شیکردنەوەی هەڵە زمانی مرۆڤ.
* **بێ پرۆمپتی ئینتەراکتیڤ لە کۆنتێکستی headless.** `--yes` (یان `-y`) بدە بە فەرمانە تێکدەرەکان؛ `--api-key` بدە یان `OMI_API_KEY` دابنێ بۆ بازدانی چوونەژوورەوەی ئینتەراکتیڤ.
* **هەڵسوکەوتی لێبووردەی دووبارەکردنەوە.** `429` و `5xx` بە backoff دووبارە دەکرێنەوە پێش دەرکەوتن.

## ڕەسەنایەتی (یەکجار، لەلایەن مرۆڤەوە)

بەکارهێنەر کلیلێکی dev API لە ئەپی وێبی Omi وەردەگرێت (`https://app.omi.me` → Developer → API Keys) و یەکێکیان هەڵدەبژێرێت:
```bash
omi auth login                          # دانانی ئینتەراکتیڤ؛ کلیلەکە لە مێژووی شێڵ نییە
# یان
export OMI_API_KEY=omi_dev_...          # کاتی، گونجاو بۆ کۆنتێنەر
```

## ئەو پێنج شتەی بریکارەکان زۆرترین جار دەیبکەن

### 1. خوێندنەوەی بیرگەکان
```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. دروستکردنی بیرگە
```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. خوێندنەوەی گفتوگۆکان
```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. خوێندنەوەی بڕگە چالاکییە کراوەکان
```bash
omi action-item list --json --open
```

### 5. نیشانکردنی بڕگە چالاکییەک وەک تەواوبوو
```bash
omi action-item complete --json a1b2c3d4
```

## API ی لوکاڵی دێسکتۆپ

کاتێک Omi Desktop API ی لوکاڵی خۆی ئاشکرا دەکات، بریکارەکان دەتوانن مێژووی شاشەی لەسەر ئامێر، کورتەکان، SQL و ئەرکەکان بپرسن بەبێ بەکارهێنانی API ی گەشەپێدەری هەور:
```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# یان، بۆ دانیشتنە کاتییەکان:
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

تەنها کاتێک ئەرکەکان تەواو بکە یان بیانسڕەوە کە بەکارهێنەر بە ڕوونی داوای بکات:
```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` سکریینشۆتەکە لەسەر دیسک دەنووسێت و هێشتا JSON چاپ دەکات بۆ stdout بۆ سکریپتەکان. ID ی سکریینشۆتەکە بە گشتی لە `local search-screen` یان SQL لەسەر خشتەی `screenshots` دێت. ئەگەر Desktop شکستی پێکهاتەیی وەک `screenshot_pending`، `screenshot_file_missing` یان `screenshot_chunk_corrupted` بگەڕێنێتەوە، مۆدی JSON خانەکانی `reason`، `hint` و `screenshot_id` لەسەر stderr دەهێڵێتەوە بۆ ئەوەی بریکارەکان ID یەکی کۆنتر دووبارە تاقی بکەنەوە یان ڕێگرەکە بە وردی ڕاپۆرت بکەن. دەرچووە سەرکەوتووەکان بە `file PATH` پشتڕاست بکەرەوە پێش ئەوەی بیاندەیتە ئامرازەکانی بینین.
```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """بانگکردنی omi CLI لە مۆدی JSON، هەڵە هەڵدەدات لە کاتی کۆدی دەرچوونی ناسەرکەوتوو."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI یەکە هەڵە پێکهاتەیییەکان چاپ دەکات لەسەر stderr لە مۆدی JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# هەموو بڕگە چالاکییە کراوەکان بخوێنەرەوە و هەر شتێک کە لە 30 ڕۆژ کۆنترە وەک تەواوبوو نیشان بکە.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## مامەڵە لەگەڵ سنوورەکانی ڕێژە

Memories: 120/hr. Conversations: 25/hr. Batch creates: 15/hr.
```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # سنووری ڕێژە
    err = json.loads(result.stderr)
    # err["detail"] وەک ئەمە دەردەکەوێت: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ئامۆژگارییەکان

* `--profile <name>` بەکاربهێنە ئەگەر بریکارەکەت چەند هەژمارێکی Omi هەڵدەگرێت. هەر پرۆفایلێک بڕوانامە و بنەڕەتی API ی خۆی هەیە.
* `--api-base http://localhost:8080` بەکاربهێنە بۆ تاقیکردنەوەی backend ی لوکاڵ.
* `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` بەکاربهێنە بۆ جێگرەوەی ڕێکخستنەکانی API ی Desktop ی پرۆفایل بۆ یەک جار جێبەجێکردن.
* `--verbose` بەکاربهێنە بۆ دیباگکردن — ئەو `METHOD path → status (Ns)` لەسەر stderr تۆمار دەکات بەبێ کاریگەری لەسەر stdout، بۆیە مۆدی JSON بە دروستی دەمێنێتەوە.
* بۆ پایپکردنی ناوەڕۆک بۆ ناو گفتوگۆیەک، `--text -` بەکاربهێنە:
```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
