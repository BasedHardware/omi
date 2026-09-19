# omi-cli עבור סוכנים (Agents)

> מדריך מעשי עבור מערכות מונעות LLM (כגון Claude Code, Cursor ובוטים עצמאיים).

## מדוע ממשק ה-CLI מותאם לסוכנים

* **חוזה JSON יציב.** הדגל `--json` פולט מסמך JSON תקני ל-stdout ורק
  מסמך JSON בלבד — ללא הודעות התקדמות או אנימציות טעינה. שגיאות מועברות ל-stderr
  במבנה `{"error": "...", "detail": "..."}`.
* **קודי יציאה יציבים.** `0` תקין / `1` שימוש שגוי / `2` שגיאת אימות / `3` שגיאת שרת / `4` חריגת קצב / `5` לא נמצא. סוכנים יכולים להסתעף ישירות על סמך קודים אלה ללא צורך בניתוח טקסט חופשי.
* **ללא הנחיות אינטראקטיביות בסביבות אוטומטיות.** העבר `--yes` (או `-y`) לפעולות הרסניות;
  העבר `--api-key` או הגדר את `OMI_API_KEY` כדי לדלג על התחברות אינטראקטיבית.
* **התנהגות ניסיון חוזר סלחנית.** שגיאות `429` ו-`5xx` מנוסות שוב עם השהיה מדורגת
  טרם החזרת השגיאה.

## אימות (חד-פעמי, על ידי האדם)

המשתמש מפיק מפתח API למפתחים מאפליקציית ה-Web של Omi
(`https://app.omi.me` → Developer → API Keys) ובוחר באחת האפשרויות:

```bash
omi auth login                          # הדבקה אינטראקטיבית; המפתח אינו נשמר בהיסטוריית הטרמינל
# או
export OMI_API_KEY=omi_dev_...          # זמני, מותאם לקונטיינרים
```

## חמשת הדברים שסוכנים מבצעים בתדירות הגבוהה ביותר

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

### 4. קריאת משימות פתוחות לביצוע

```bash
omi action-item list --json --open
```

### 5. סימון משימה כהושלמה

```bash
omi action-item complete --json a1b2c3d4
```

## ממשק Desktop API מקומי

כאשר Omi Desktop חושף את ה-API המקומי שלו, סוכנים יכולים לתשאל היסטוריית מסך מקומית,
סיכומים, שאילתות SQL ומשימות מבלי להשתמש ב-API של הענן:

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

השלם או מחק משימות רק כאשר המשתמש מבקש זאת במפורש:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

הפקודה `omi local screenshot SCREENSHOT_ID --output PATH` שומרת את צילום המסך בדיסק
וממשיכה להדפיס פלט JSON ל-stdout עבור סקריפטים. מזהה צילום המסך מתקבל בדרך כלל
מ-`local search-screen` או משאילתת SQL בטבלת `screenshots`. אם תוכנת ה-Desktop
מחזירה שגיאה מובנית כגון `screenshot_pending`, `screenshot_file_missing`
או `screenshot_chunk_corrupted`, מצב JSON שומר על השדות `reason`, `hint`
ו-`screenshot_id` ב-stderr כדי שסוכנים יוכלו לנסות שוב עם מזהה ישן יותר או לדווח
על החסימה המדויקת. ודא פלטים תקינים באמצעות `file PATH` לפני העברתם למודלים חזותיים.

## דוגמה מעשית: לולאת סוכן בפייתון

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """מפעיל את ה-CLI של omi במצב JSON ומעלה חריגה בעת קודי שגיאה."""
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
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# קורא את כל המשימות הפתוחות ומסמן כהושלמו משימות בנות מעל 30 יום.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## טיפול במגבלות קצב (rate limits)

זיכרונות: 120 לשעה. שיחות: 25 לשעה. יצירה מרוכזת: 15 לשעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # הוגבל קצב
    err = json.loads(result.stderr)
    # הערך של err["detail"] נראה כך: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפים

* השתמש בדגל `--profile <שם>` אם הסוכן שלך מנהל חשבונות Omi מרובים. לכל
  פרופיל יש נתוני אימות וכתובת API ייעודיים.
* השתמש ב-`--api-base http://localhost:8080` עבור בדיקות שרת מקומיות.
* השתמש במשתנים `OMI_LOCAL_API_URL` ו-`OMI_LOCAL_TOKEN` כדי לעקוף הגדרות מקומיות
  של ה-Desktop API עבור הפעלה בודדת.
* השתמש ב-`--verbose` לניפוי שגיאות — נרשם `METHOD path → status (Ns)` ל-stderr
  מבלי להשפיע על stdout, כך שמצב JSON נשאר תקני לחלוטין.
* להעברת תוכן לתוך שיחה באמצעות צינור (pipe), השתמש ב-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
