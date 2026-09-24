# omi-cli עבור אג'נטים

> מדריך מעשי לסביבות הנעות על ידי LLM (Claude Code, Cursor, הבוטים שלכם).

## למה ה-CLI ידידותי לאג'נטים

* **חוזה JSON יציב.** `--json` פולט מסמך JSON תקין ל-stdout וגם
  *רק* מסמך JSON — ללא הודעות התקדמות, ללא ספינרים. שגיאות הולכות ל-
  stderr כ-`{"error": "...", "detail": "..."}`.
* **קודי יציאה יציבים.** `0` תקין / `1` שגיאת שימוש / `2` שגיאת אימות / `3` שגיאת שרת / `4` הוגבל
  קצב / `5` לא נמצא. אג'נטים יכולים להתפצל לפי קודי האלה בלי לפענח
  שגיאות בשפה טבעית.
* **בלי פרומפטים אינטראקטיביים במצב headless.** העבירו `--yes` (או `-y`)
  לפקודות הרסניות; העבירו `--api-key` או הגדרו `OMI_API_KEY` כדי לדלג על
  הכניסה האינטראקטיבית.
* **התנהגות ניסיונות סלחנית.** `429` ו-`5xx` מנסים שוב עם backoff
  לפני שהם מוצגים.

## אימות (פעם אחת, על ידי האדם)

המשתמש מפתח מפתח API למפתחים מאפליקציית האינטרנט של Omi
(`https://app.omi.me` → Developer → API Keys) ואחד מהשניים:

```bash
omi auth login                          # הדבקה אינטראקטיבית; המפתח לא נשמר בהיסטוריית ה-shell
# או
export OMI_API_KEY=omi_dev_...          # זמני, ידידותי ל-containers
```

## חמש הפעולות שהאג'נטים עושים הכי הרבה

### 1. קריאת memories

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. יצירת memory

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. קריאת שיחות

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. קריאת action items פתוחים

```bash
omi action-item list --json --open
```

### 5. סימון action item כהושלם

```bash
omi action-item complete --json a1b2c3d4
```

## API מקומי של Desktop

כאשר Omi Desktop חושף את ה-API המקומי שלו, אג'נטים יכולים לשאול היסטוריית מסך
במכשיר, תקצירים, SQL ומשימות בלי להשתמש ב-cloud dev API:

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

השלימו או מחקו משימות רק כשהמשתמש מבקש במפורש:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` כותב את צילום המסך ל-
דיסק ועדיין מדפיס JSON ל-stdout עבור סקריפטים. מזהה הצילום בדרך כלל מגיע
מ-`local search-screen` או מ-SQL על טבלת `screenshots`. אם Desktop
מחזיר כשל מובנה כגון `screenshot_pending`, `screenshot_file_missing`
או `screenshot_chunk_corrupted`, מצב JSON שומר את השדות `reason`, `hint` ו-
`screenshot_id` ב-stderr כדי שאג'נטים יוכלו לנסות מזהה ישן יותר או לדווח על
החסם המדויק. אמתו פלטים מוצלחים עם `file PATH` לפני שאתם מעבירים אותם
לכלי ראייה.

## דוגמה מעשית: לולאת אג'נט Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """מריץ את omi CLI במצב JSON, מעלה שגיאה בקודי יציאה לא-אפס."""
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

# קרא את כל ה-action items הפתוחים והשלם כל פריט שגילו מעל 30 יום.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## טיפול במגבלות קצב

Memories: 120/שעה. Conversations: 25/שעה. יצירות באצווה: 15/שעה.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # הוגבל קצב
    err = json.loads(result.stderr)
    # err["detail"] נראה כמו: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## טיפים

* השתמשו ב-`--profile <שם>` אם האג'נט מנהל כמה חשבונות Omi. לכל
  פרופיל יש תעודות ו-base API משלו.
* השתמשו ב-`--api-base http://localhost:8080` לבדיקת backend מקומי.
* השתמשו ב-`OMI_LOCAL_API_URL` ו-`OMI_LOCAL_TOKEN` כדי לדרס הגדרות
  של API Desktop לפי פרופיל לריצה אחת.
* השתמשו ב-`--verbose` לניפוי — זה רושם `METHOD path → status (Ns)` ל-stderr
  בלי להשפיע על ה-stdout, כך ש-JSON mode נשאר תקין.
* להעברת תוכן לתוך שיחה דרך צינור, השתמשו ב-`--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
