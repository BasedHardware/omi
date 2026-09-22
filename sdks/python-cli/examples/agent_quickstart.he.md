# omi-cli לסוכני בינה מלאכותית

> מדריך מעשי לסביבות מבוססות מודלי שפה (Claude Code, Cursor, בוטים מותאמים אישית).

## מדוע ה-CLI מותאם במיוחד לסוכנים

* **חוזה JSON יציב:** הדגל `--json` פולט מסמך JSON תקני ל-stdout ו*רק* JSON — ללא הודעות סטטוס או ספינרים. שגיאות נשלחות ל-stderr במבנה `{"error": "...", "detail": "..."}`.
* **קודי יציאה יציבים:** `0` תקין / `1` שגיאת שימוש / `2` שגיאת אימות / `3` שגיאת שרת / `4` חריגה ממגבלת קצב / `5` לא נמצא. סוכנים יכולים להסתעף ישירות לפי קוד היציאה ללא צורך בניתוח טקסט חופשי.
* **ללא פקודות אינטראקטיביות במצב ללא ראש (Headless):** העבר `--yes` (או `-y`) עבור פקודות הרסניות; העבר `--api-key` או הגדר את `OMI_API_KEY` כדי לעקוף התחברות אינטראקטיבית בדפדפן.
* **מנגנון ניסיון חוזר אוטומטי:** שגיאות `429` ו-`5xx` מנוסות מחדש אוטומטית עם השהיה מעריכית לפני החזרת כשל.

## אימות (חד-פעמי על ידי אדם)

המשתמש מפיק מפתח API למפתחים באפליקציית הרשת של Omi
(`https://app.omi.me` → Developer → API Keys), ומריץ:

```bash
omi auth login                          # הדבקה אינטראקטיבית; המפתח אינו נשמר בהיסטוריית ה-shell
# או
export OMI_API_KEY=omi_dev_...          # זמני, מתאים למכולות ו-CI/CD
```

## חמש הפעולות הנפוצות ביותר של סוכנים

### 1. קריאת זיכרונות (Memories)

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

### 4. קריאת משימות פתוחות (Action Items)

```bash
omi action-item list --json --open
```

### 5. השלמת משימה

```bash
omi action-item complete --json a1b2c3d4
```

## ממשק API מקומי לשולחן העבודה (Local Desktop API)

כאשר Omi Desktop חושף את ה-API המקומי שלו, סוכנים יכולים לתשאל היסטוריית מסך, סיכומים, SQL ומשימות ללא תלות בענן:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# או להפעלות זמניות:
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

השלם או מחק משימות רק כאשר המשתמש מבקש זאת במפורש:

השלם או מחק משימות רק כאשר המשתמש מבקש זאת במפורש:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` שומר את צילום המסך בדיסק ועדיין מדפיס JSON ל-stdout עבור סקריפטים. מזהה צילום המסך מגיע בדרך כלل מ-`local search-screen` או שאילתת SQL על טבלת `screenshots`. אם אפליקציית Desktop מחזירה שגיאה מובנית כמו `screenshot_pending`, `screenshot_file_missing`, או `screenshot_chunk_corrupted`, מצב JSON שומר על השדות `reason`, `hint`, ו-`screenshot_id` ב-stderr כדי שסוכנים יוכלו לנסות שוב עם מזהה ישן יותר או לדווח על החסימה המדויקת. אמת פלטים מוצלחים עם `file PATH` לפני העברתם לכלי ראייה ממוחשבת.

## דוגמה מעשית: לולאת סוכן פייתון (Python)

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

## ניהול מגבלות קצב (Handling rate limits)

זיכרונות: 120/שעה. שיחות: 25/שעה. יצירת אצוות: 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפים שימושיים (Tips)

* השתמש ב-`--profile <name>` אם הסוכן שלך מנהל מספר חשבונות Omi. לכל פרופיל יש אישורים וכתובת API משלו.
* השתמש ב-`--api-base http://localhost:8080` לבדיקות מול שרת מקומי.
* השתמש ב-`OMI_LOCAL_API_URL` ו-`OMI_LOCAL_TOKEN` כדי לעקוף את הגדרות Desktop API של הפרופיל להרצה אחת.
* השתמש ב-`--verbose` לניפוי שגיאות — מדפיס ל-stderr מבלי להשפיע על stdout, כך שפורמט ה-JSON נשאר תקין.
* להזרמת תוכן לשיחה דרך צינור (pipe), השתמש ב-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
