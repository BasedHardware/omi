# מדריך התחלה מהירה עבור omi-cli (Hebrew Quickstart Guide)

> מדריך מעשי לעבודה עם Omi מהמסוף — מיועד למשתמשים ולסוכני AI כאחד.

`omi-cli` הוא ממשק שורת הפקודה הרשמי לעבודה עם ה-API של [Omi](https://omi.me).
הכלי מאפשר לנהל בצורה נוחה וידידותית לתסריטים (scripts) את ארבעת משאבי הליבה של Omi: זיכרונות, שיחות, משימות לביצוע ויעדים.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **תיעוד רשמי:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **קוד מקור:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. התקנה (Installation)

דרך ההתקנה המומלצת היא באמצעות `pipx`, המבודד את התלויות בסביבה ייעודית:

```bash
# התקנה מומלצת באמצעות pipx
pipx install omi-cli

# לחלופין, התקנה באמצעות pip
pip install omi-cli
```

> **חשוב: הבחנה בין שם החבילה לשם הפקודה**
> * שם חבילת ה-Python להתקנה הוא **`omi-cli`** (השם `omi` שייך לחבילה נפרדת שאינה קשורה).
> * הפקודה שמריצים במסוף לאחר ההתקנה היא **`omi`**.

לאחר ההתקנה, מומלץ לוודא את תקינות הכלי:

```bash
omi --version
omi --help
```

---

## 2. אימות (Authentication)

`omi-cli` תומך בשתי שיטות אימות עיקריות:

| שיטת אימות | שימוש עיקרי | דוגמת פקודה |
| :--- | :--- | :--- |
| **מפתח API למפתחים (`omi_dev_*`)** | CI/CD, סקריפטים אוטומטיים וסוכני AI | `omi auth login --api-key ...` או משתנה סביבה |
| **אימות בדפדפן (OAuth דרך Google/Apple)** | מחשב פיתוח אישי ותחנות עבודה מקומיות | `omi auth login --browser` |

### התחברות אינטראקטיבית
הפעלת הפקודה ללא דגלים תציג תפריט לבחירת שיטת ההתחברות:

```bash
omi auth login
# 1) Browser — התחברות בדפדפן באמצעות Google או Apple (מומלץ למשתמשים)
# 2) API key — הדבקת מפתח מפתח מאתר app.omi.me (מומלץ לסוכנים/CI)
```

### התחברות ישירה באמצעות דפדפן
```bash
omi auth login --browser
```

### התחברות באמצעות מפתח API
ניתן להנפיק מפתח API בממשק המפתחים בכתובת [app.omi.me](https://app.omi.me) תחת Developer ← API Keys:

```bash
# הגדרה ישירה באמצעות הפקודה
omi auth login --api-key omi_dev_...

# או הגדרה באמצעות משתנה סביבה (מתאים ל-CI/CD ולמכולות)
export OMI_API_KEY=omi_dev_...
```

### בדיקת מצב האימות
* `omi auth status`: מציג את פרופיל האימות המקומי, תוקף הטוקן וערך מוסתר חלקית (עובד במצב לא מקוון).
* `omi auth whoami`: שולח בקשת אימות לשרתי Omi כדי לוודא שהאישורים תקפים (דורש חיבור לרשת).

```bash
omi auth status
omi auth whoami
```

להתנתקות ומחיקת האישורים המקומיים:
```bash
omi auth logout
```

---

## 3. שימוש בסיסי (Basic Usage)

ניתן להציג ולנהל את ארבעת משאבי הליבה של Omi:

### זיכרונות (Memories)
עובדות ותובנות שנלמדו ונשמרו על ידי המערכת:

```bash
# הצגת רשימת הזיכרונות
omi memory list

# יצירת זיכרון חדש
omi memory create "User prefers dark mode" --category lifestyle

# צפייה בפרטי זיכרון ספציפי
omi memory get <MEMORY_ID>
```

### שיחות (Conversations)
היסטוריית שיחות והקלטות שמע ממכשירי Omi ומאפליקציות נלוות:

```bash
# הצגת 5 השיחות האחרונות
omi conversation list --limit 5

# צפייה בפרטי שיחה כולל תמלול מלא
omi conversation get <CONVERSATION_ID> --include-transcript
```

### משימות לביצוע (Action Items)
משימות שחולצו אוטומטית מתוך השיחות:

```bash
# הצגת משימות פתוחות בלבד
omi action-item list --open

# סימון משימה כהושלמה
omi action-item complete <ACTION_ITEM_ID>
```

### יעדים (Goals)
מעקב אחר מטרות ויעדים אישיים:

```bash
# הצגת רשימת היעדים
omi goal list
```

---

## 4. עבודה עם סקריפטים ופלט JSON‏ (`--json`)

`omi-cli` תומך בפלט JSON מובנה עבור כל הפקודות. בעבודה עם כלי עיבוד כגון `jq` או סקריפטים ב-Python, יש להעביר את הדגל `--json` כדגל **גלובלי** לפני פקודת המשנה:

```bash
# קבלת רשימת זיכרונות בפורמט JSON וחילוץ מזהה ותוכן
omi --json memory list | jq '.[] | {id, content, category}'

# קבלת כותרות 5 השיחות האחרונות
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# הצגת משימות פתוחות בפורמט JSON
omi --json action-item list --open | jq '.'
```

> **דגש חשוב:** הדגל `--json` חייב להופיע **לפני** פקודת המשנה (כגון `memory` או `conversation`):
> * נכון: `omi --json memory list`
> * שגוי: `omi memory list --json`

---

## 5. קודי סיום (Exit Codes)

לקבלת התנהגות עקבית ואמינה בסקריפטים ובצינורות אוטומציה, מוגדרים קודי סיום ייעודיים:

| קוד סיום | משמעות | פירוט |
| :---: | :--- | :--- |
| `0` | הצלחה (Success) | הפקודה הושלמה בהצלחה מלאה |
| `1` | שגיאת שימוש (Usage Error) | דגלים שגויים או חוסר בארגומנטים נדרשים |
| `2` | שגיאת אימות (Auth Error) | לא מחובר, מפתח API לא תקף או פג תוקף |
| `3` | שגיאת שרת (Server Error) | שגיאת 5xx, פסק זמן (timeout) או בעיית תקשורת |
| `4` | הגבלת קצב (Rate Limited) | שגיאת 429 Too Many Requests |
| `5` | משאב לא נמצא (Not Found) | שגיאת 404 Not Found (המזהה המבוקש אינו קיים) |

---

## 6. דוגמאות לפי סביבת מעטפת (Shell Examples)

### Bash / Zsh (Linux / macOS)
```bash
# הגדרת מפתח ה-API
export OMI_API_KEY="omi_dev_your_actual_key_here"

# שליפת נתונים
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# הגדרת מפתח ה-API
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# פיענוח JSON ב-PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. חיבור ל-API המקומי של Desktop

בסביבות שבהן אפליקציית Omi Desktop פועלת, ניתן לגשת ישירות להיסטוריית המסך ולמסד הנתונים המקומי ללא תלות בענן:

```bash
# הגדרת כתובת וטוקן ל-API המקומי
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# בדיקת מצב חיבור מקומי
omi --json local status

# חיפוש בהיסטוריית המסך המקומית
omi --json local search-screen "pricing" --days 7 --app Safari
```

---

## 8. ניהול פרופילים (Profiles)

כאשר מנהלים מספר חשבונות או סביבות בדיקה וייצור נפרדות, ניתן להשתמש בדגל `--profile`. ההגדרות נשמרות בקובץ `~/.omi/config.toml`:

```bash
# התחברות לפרופיל אישי
omi --profile personal auth login

# התחברות לפרופיל עבודה
omi --profile work auth login

# הפעלת פקודות תחת פרופיל מסוים
omi --profile work memory list
```
