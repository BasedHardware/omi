# omi-cli עבור סוכנים (Agents)

> מדריך מעשי עבור סביבות מבוססות LLM (כגון Claude Code, Cursor ובוטים ייעודיים).

## מדוע ה-CLI מותאם במיוחד לסוכנים

* **חוזה JSON יציב.** הדגל `--json` פולט מסמך JSON תקין ל-stdout ו*אך ורק*
  מסמך JSON — ללא הודעות התקדמות או ספינרים. שגיאות מועברות ל-stderr
  במבנה `{"error": "...", "detail": "..."}`.
* **קודי יציאה יציבים.** `0` תקין / `1` שגיאת שימוש / `2` שגיאת אימות / `3` שגיאת שרת / `4` חריגה
  ממגבלת קצב (rate limited) / `5` לא נמצא. סוכנים יכולים להסתעף לפי קודים אלו ללא צורך בניתוח שגיאות בשפה טבעית.
* **ללא פניות אינטראקטיביות בהרצה אוטונומית (headless).** העבירו `--yes` (או `-y`)
  עבור פקודות הרסניות; העבירו `--api-key` או הגדירו את `OMI_API_KEY` כדי לדלג על התחברות ידנית.
* **התנהגות ניסיון חוזר סובלנית.** שגיאות מסוג `429` ו-`5xx` מנוסות מחדש באופן אוטומטי עם השהיה מעריכית (backoff)
  טרם החזרת הכישלון.

## אימות (חד-פעמי, מבוצע על ידי המשתמש)

המשתמש מקבל מפתח API למפתחים מאפליקציית הרשת של Omi
(`https://app.omi.me` → Developer → API Keys) ובוחר באחת הדרכים:

```bash
omi auth login                          # הדבקה אינטראקטיבית; המפתח לא נשמר בהיסטוריית ה-shell
# או
export OMI_API_KEY=omi_dev_...          # זמני ומתאים לסביבות קונטיינרים
```

## חמש הפעולות הנפוצות ביותר בקרב סוכנים

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

### 4. קריאת משימות פתוחות

```bash
omi action-item list --json --open
```

### 5. סימון משימה כהושלמה

```bash
omi action-item complete --json a1b2c3d4
```

## API מקומי של Desktop

כאשר Omi Desktop חושף את ה-API המקומי שלו, סוכנים יכולים לתשאל היסטוריית
מסך על המכשיר, סיכומים, שאילתות SQL ומשימות מבלי לצרוך את ה-API בענן:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# או עבור הפעלות זמניות:
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

השלימו או מחקו משימות אך ורק כאשר המשתמש מבקש זאת מפורשות:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

הפקודה `omi local screenshot SCREENSHOT_ID --output PATH` שומרת את צילום המסך
לדיסק וממשיכה להדפיס פלט JSON ל-stdout עבור סקריפטים. מזהה צילום המסך מגיע לרוב
מ-`local search-screen` או משאילתת SQL על טבלת `screenshots`. אם Desktop מחזיר
שגיאה מובנית כמו `screenshot_pending`, `screenshot_file_missing` או
`screenshot_chunk_corrupted`, מצב JSON שומר על השדות `reason`, `hint` ו-
`screenshot_id` ב-stderr כדי שסוכנים יוכלו לנסות שוב עם מזהה ישן יותר או לדווח על
החסם המדויק. אמתו קבצים שהושלמו בהצלחה באמצעות `file PATH` לפני העברתם לכלי ראייה ממוחשבת.

## דוגמה מעשית: לולאת סוכן בפייתון

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """מריץ את ה-CLI של omi במצב JSON, ומעלה שגיאה עבור קוד יציאה שאינו 0."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # ה-CLI מדפיס שגיאות מובנות ל-stderr במצב JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi הסתיים עם קוד {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# קריאת כל המשימות הפתוחות וסימון כהושלמו של כל משימה שנוצרה לפני יותר מ-30 יום.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## ניהול מגבלות קצב (Rate limits)

זיכרונות: 120/שעה. שיחות: 25/שעה. יצירה באצוות: 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # מגבלת קצב נחצתה
    err = json.loads(result.stderr)
    # השדה err["detail"] נראה בערך כך: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפים

* השתמשו ב-`--profile <name>` אם הסוכן שלכם מנהל מספר חשבונות Omi. לכל
  פרופיל אישורי כניסה ובסיס API משלו.
* השתמשו ב-`--api-base http://localhost:8080` עבור בדיקות מול שרת מקומי.
* השתמשו ב-`OMI_LOCAL_API_URL` וב-`OMI_LOCAL_TOKEN` כדי לעקוף את הגדרות
  ה-API המקומי של הפרופיל עבור הרצה בודדת.
* השתמשו ב-`--verbose` לצורכי ניפוי שגיאות — רושם `METHOD נתיב → סטטוס (Ns)` ל-stderr
  מבלי להשפיע על stdout, כך שמבנה ה-JSON נשמר תקין.
* להזרמת תוכן לתוך שיחה באמצעות pipe, השתמשו ב-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
