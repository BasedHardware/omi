# omi-cli بۆ ئەیجەنتەکان

> ڕێنمایی پراکتیکی بۆ harnessـەکانی بە LLM کارەکەر (Claude Code، Cursor، بۆتەکانی خۆتان).

## بۆچی ئەم CLIـیە بۆ ئەیجەنت گونجاوە

* **گرێبەستی JSON جێگیرە.** `--json` بەڵگەنامەیەکی JSONـی دروست دەنێرێتە
  stdout و *تەنیا* بەڵگەنامەی JSON — بەبێ نامەکانی پێشکەوتن، بەبێ spinner.
  هەڵەکان بە `{"error": "...", "detail": "..."}` دەچنە stderr.
* **کۆدەکانی دەرچوون جێگیرن.** `0` سەرکەوتوو / `1` هەڵەی بەکارهێنان / `2`
  هەڵەی ڕەسەنێت / `3` هەڵەی سێرڤەر / `4` سنووردارکراو / `5` نەدۆزرایەوە.
  ئەیجەنتەکان دەتوانن لەسەر ئەمانە لاک بدەن بەبێ پەڕەپارسکردنی هەڵە
  زمانییە سروشتییەکان.
* **لە ژوورەوە headless پرسیار نییە.** بۆ فەرمانە تێکدەرەکان `--yes` (یان `-y`)
  بنێرە؛ `--api-key` بنێرە یان `OMI_API_KEY` دابنێ بۆ تێپەڕاندنی چوونەژوورەوە.
* **دووبارەکەوتنەوە بەخشەرانەیە.** `429` و `5xx` پێش دەرکەوتن بە backoff
  دووبارە دەکرێنەوە.

## ڕەسەنێت (تەنیا جارێک، لەلایەن کەسێکەوە)

بەکارهێنەر dev API key لە ئەپی وێبی Omi وەردەگرێت
(`https://app.omi.me` → Developer → API Keys) و یەکێک لەمانە دەکات:

```bash
omi auth login                          # لکێنانی کارلێکەرانە؛ کلیل ناچێتە مێژووی shell
# یان
export OMI_API_KEY=omi_dev_...          # کاتی، گونجاوە بۆ کۆنتەینەر
```

## پێنج شتەکەی ئەیجەنتەکان زۆرترین جار دەیانکەن

### 1. خوێندنەوەی memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. دروستکردنی memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. خوێندنەوەی conversations

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. خوێندنەوەی action itemە کراوەکان

```bash
omi action-item list --json --open
```

### 5. نیشانەکردنی action item وەک تەواوبوو

```bash
omi action-item complete --json a1b2c3d4
```

## APIـی لوکاڵی Desktop

کاتێک Omi Desktop APIـی لوکاڵەکەی دەردەخات، ئەیجەنتەکان دەتوانن بەبێ بەکارهێنانی
ئەپی گەشەپێدەری هەوری، مێژووی شاشە، recap، SQL و taskەکانی سەر ئامێرەکە بپرسن:

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

تەنیا کاتێک بەکارهێنەر بەڕوونی داوا دەکات، taskەکان تەواو یان بسڕەوە:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` وێنەی شاشەکە دەنوسێتە
سەر دیسک و هێشتا بۆ سکرێپتەکان JSON دەچەسپێنێتە stdout. ناسنامەی وێنەی شاشە
زۆرجار لە `local search-screen` یان SQLـی سەر خشتەی `screenshots` دێت.
ئەگەر Desktop شکستێکی پێکدێنراو وەک `screenshot_pending`،
`screenshot_file_missing` یان `screenshot_chunk_corrupted` بگەڕێنێتەوە،
JSON mode خانەکانی `reason`، `hint` و `screenshot_id` لە stderr دەپارێزێت
بۆ ئەوەی ئەیجەنت ناسنامەیەکی کۆنتر دووبارە بکاتەوە یان بەدوورگەی ڕێگرییەکە
بپوختە ڕاپۆرت بکات. دەرچوونە سەرکەوتووەکان پێش دانان بە ئامرازە بینینەکان
بە `file PATH` پشتڕاست بکەرەوە.

## نموونەی تەواوکراو: ئاردی Python agent

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """لە JSON mode omi CLI بانگهێشت بکە، ئەگەر کۆدی دەرچوون سەرکەوتوو نەبوو هەڵە هەڵدەدات."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # لە JSON mode CLI هەڵە پێکدێنراوەکان دەنوسێتە stderr:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# هەموو action itemە کراوەکان بخوێنەوە و هەر شتێک کە لە ٣٠ ڕۆژ کۆنترە تەواوی بکە.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## بەڕێوەبردنی سنووردارکردنی ڕێژە

Memories: ١٢٠/کاتژمێر. Conversations: ٢٥/کاتژمێر. دروستکردنی کۆمەڵە: ١٥/کاتژمێر.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # سنووردارکراو
    err = json.loads(result.stderr)
    # err["detail"] وەک ئەمە دەربکەوێت: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## ئامرازییەکان

* ئەگەر ئەیجەنتەکەت چەند هەژمارێکی Omi بەڕێوە دەبات، `--profile <name>` بەکاربهێنە.
  هەر پرۆفایلێک کریدێنشاڵ و API baseـی خۆی هەیە.
* بۆ تاقیکردنەوەی باەکێندی لوکاڵ `--api-base http://localhost:8080` بەکاربهێنە.
* بۆ سەرنووسکردنی ڕێکخستنەکانی Desktop APIـی پرۆفایل تەنیا بۆ یەک جێبەجێکردن،
  `OMI_LOCAL_API_URL` و `OMI_LOCAL_TOKEN` بەکاربهێنە.
* بۆ debugging `--verbose` بەکاربهێنە — `METHOD path → status (Ns)` دەنوسێتە
  stderr بەبێ کارگەیانکردن لە stdout، بۆ ئەوەی JSON mode دروست بمێنێتەوە.
* بۆ ڕەوانەکردنی ناوەڕۆک بۆ ناو conversation، `--text -` بەکاربهێنە:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
