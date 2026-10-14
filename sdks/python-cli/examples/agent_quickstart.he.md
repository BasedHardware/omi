# omi-cli לסוכנים

> מדריך מעשי ל-harnesses מונחי LLM (Claude Code, Cursor, הבוטים שלך).

## למה ה-CLI ידידותי לסוכנים

* **חוזה JSON יציב.** `--json` פולט מסמך JSON תקף ל-stdout ו-*רק* מסמך JSON —
  בלי הודעות התקדמות, בלי ספינרים. שגיאות הולכות ל-stderr כ-`{"error": "...", "detail": "..."}`.
* **קודי יציאה יציבים.** `0` תקין / `1` שימוש / `2` auth / `3` שרת /
  `4` מגבלת קצב / `5` לא נמצא. סוכנים יכולים לפצל על אלה בלי לנתח שגיאות
  בשפה טבעית.
* **בלי prompts אינטראקטיביים בהקשרים headless.** העבר `--yes` (או `-y`) לפקודות
  הרסניות; העבר `--api-key` או הגדר `OMI_API_KEY` כדי לדלג על התחברות אינטראקטיבית.
* **התנהגות ניסיון-חוזר סלחנית.** `429` ו-`5xx` מנסים שוב עם backoff לפני שהם צפים.

## Auth (פעם אחת, על ידי האדם)

המשתמש מקבל מפתח dev API מאפליקציית ה-web של Omi
(`https://app.omi.me` → Developer → API Keys) ואו:

```bash
omi auth login                          # הדבקה אינטראקטיבית; המפתח לא נשאר בהיסטוריית ה-shell
# או
export OMI_API_KEY=omi_dev_...          # חולף, אידיאלי לקונטיינרים
```

## חמשת הדברים שסוכנים עושים הכי הרבה

### 1. קריאת זיכרונות

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. יצירת זיכרון

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. קריאת שיחות

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. קריאת פריטי פעולה פתוחים

```bash
omi action-item list --json --open
```

### 5. סימון פריט פעולה כבוצע

```bash
omi action-item complete --json a1b2c3d4
```

## API מקומי של Desktop

כש-Omi Desktop חושף את ה-API המקומי שלו, סוכנים יכולים לשאול את היסטוריית
המסך במכשיר, תקצירים, SQL ומשימות בלי להשתמש ב-API dev של הענן:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# או, לסשנים חולפים:
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

השלם או מחק משימות רק כשהמשתמש מבקש במפורש:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` כותב את צילום המסך לדיסק
ועדיין מדפיס JSON ל-stdout עבור סקריפטים. מזהה צילום המסך מגיע בדרך כלל מ-`local
search-screen` או SQL על הטבלה `screenshots`. אם Desktop מחזיר כשל מובנה כמו
`screenshot_pending`, `screenshot_file_missing` או `screenshot_chunk_corrupted`,
מצב JSON שומר על השדות `reason`, `hint` ו-`screenshot_id` ב-stderr כדי שסוכנים
יוכלו לנסות שוב מזהה ישן יותר או לדווח על החסימה המדויקת. אמת פלטים מוצלחים עם
`file PATH` לפני העברה לכלי ראייה.

## דוגמה מעובדת: לולאת סוכן ב-Python

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

## טיפול במגבלות קצב

זיכרונות: 120/שעה. שיחות: 25/שעה. יצירות באצווה: 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפים

* השתמש ב-`--profile <name>` אם הסוכן שלך מנהל מספר חשבונות Omi. לכל פרופיל
  יש אישורים ו-base API משלו.
* השתמש ב-`--api-base http://localhost:8080` לבדיקות backend מקומיות.
* השתמש ב-`OMI_LOCAL_API_URL` ו-`OMI_LOCAL_TOKEN` כדי לעקוף את הגדרות ה-API
  המקומי של Desktop של הפרופיל לריצה אחת.
* השתמש ב-`--verbose` לדיבוג — הוא רושם `METHOD path → status (Ns)` ל-stderr
  בלי להשפיע על stdout, כך שמצב JSON נשאר תקף.
* כדי לצנתר תוכן לשיחה, השתמש ב-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
