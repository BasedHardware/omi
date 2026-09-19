# omi-cli עבור סוכני AI

> מדריך מעשי לסביבות הרצה מבוססות מודלי שפה (Claude Code, Cursor, בוטים עצמאיים).

## מדוע ה-CLI מותאם במיוחד לסוכנים

* **חוזה JSON יציב.** הדגל `--json` פולט מסמך JSON תקין ל-stdout ו*אך ורק* מסמך
  JSON — ללא הודעות התקדמות או מחווני טעינה. שגיאות נשלחות ל-stderr במבנה
  `{"error": "...", "detail": "..."}`.
* **קודי יציאה יציבים.** `0` הצלחה / `1` שגיאת שימוש / `2` אימות / `3` שרת / `4` חריגת
  מגבלת קצב / `5` לא נמצא. סוכנים יכולים לפצל לוגיקה לפיהם ללא צורך בניתוח טקסט חופשי.
* **ללא בקשות אינטראקטיביות בסביבות Headless.** העבירו `--yes` (או `-y`) לפקודות בעלות
  השפעה הרסנית; העבירו `--api-key` או הגדירו את `OMI_API_KEY` כדי לדלג על התחברות אינטראקטיבית.
* **התנהגות ניסיון חוזר סלחנית.** שגיאות מסוג `429` ו-`5xx` מנוסות שוב אוטומטית עם השהיה
  לפני שהן מדווחות החוצה.

## אימות (חד-פעמי, על ידי אדם)

המשתמש מקבל מפתח API לפיתוח מאפליקציית הרשת של Omi
(`https://app.omi.me` ← Developer ← API Keys) ומבצע אחת מהאפשרויות:

```bash
omi auth login                          # הדבקה אינטראקטיבית; המפתח אינו נשמר בהיסטוריית ה-shell
# או
export OMI_API_KEY=omi_dev_...          # זמני ומתאים לקונטיינרים
```

## חמש הפעולות הנפוצות ביותר של סוכנים

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

### 4. קריאת משימות לביצוע פתוחות

```bash
omi action-item list --json --open
```

### 5. סימון משימת ביצוע כהושלמה

```bash
omi action-item complete --json a1b2c3d4
```

## Desktop API מקומי

כאשר Omi Desktop חושף את ה-API המקומי שלו, סוכנים יכולים לתשאל היסטוריית מסך מקומית,
סיכומים, שאילתות SQL ומשימות מבלי להשתמש ב-API של הענן:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# או, עבור הפעלות זמניות:
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

השלימו או מחקו משימות אך ורק כאשר המשתמש מבקש זאת במפורש:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

הפקודה `omi local screenshot SCREENSHOT_ID --output PATH` שומרת את צילום המסך בדיסק
וממשיכה להדפיס פלט JSON ל-stdout עבור סקריפטים. מזהה צילום המסך מגיע לרוב מ-`local search-screen`
או משאילתת SQL מעל טבלת `screenshots`. אם Desktop מחזיר כשל מובנה כגון `screenshot_pending`,
`screenshot_file_missing` או `screenshot_chunk_corrupted`, מצב ה-JSON שומר על השדות `reason`,
`hint` ו-`screenshot_id` ב-stderr כך שסוכנים יכולים לנסות מזהה ישן יותר או לדווח על החסימה המדויקת.
אמתו פלטים תקינים באמצעות `file PATH` לפני העברתם לכלי ראייה ממוחשבת (vision tools).

## דוגמה מעשית: לולאת סוכן ב-Python

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

## התמודדות עם מגבלות קצב (Rate Limits)

זיכרונות: 120/שעה. שיחות: 25/שעה. יצירות מרוכזות (Batch): 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפים

* השתמשו ב-`--profile <name>` אם הסוכן שלכם מנהל מספר חשבונות Omi במקביל. לכל
  פרופיל הגדרות אימות וכתובת API עצמאיות משלו.
* השתמשו ב-`--api-base http://localhost:8080` עבור בדיקות פיתוח מקומיות של ה-backend.
* השתמשו ב-`OMI_LOCAL_API_URL` וב-`OMI_LOCAL_TOKEN` כדי לדרוס את הגדרות ה-Desktop API
  המוגדרות בפרופיל עבור הרצה יחידה.
* השתמשו ב-`--verbose` לצורכי ניפוי שגיאות — הדגל רושם `METHOD path → status (Ns)` ל-stderr
  מבלי להשפיע על פלט ה-stdout, כך שמצב ה-JSON נותר תקין.
* להזרמת תוכן לתוך שיחה, השתמשו ב-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
