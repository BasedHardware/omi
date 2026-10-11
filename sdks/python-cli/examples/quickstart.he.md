# omi-cli — מדריך מהיר בעברית

> מדריך מעשי לעבודה עם Omi מהטרמינל. מתאים גם לאדם וגם לסוכן AI.

`omi-cli` הוא ממשק שורת הפקודה הרשמי של ה-API למפתחים של [Omi](https://omi.me).
הוא נותן גישה מהירה ומתאימה לסקריפטים לארבע הישויות המרכזיות של Omi:
זיכרונות (memories), שיחות (conversations), משימות (action items) ומטרות (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **תיעוד:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **קוד מקור:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. התקנה

הדרך המומלצת היא `pipx`: היא מתקינה את הכלי בסביבה מבודדת,
כך שהתלויות שלו לא מתנגשות עם הפרויקטים שלכם.

```bash
# מומלץ: התקנה דרך pipx
pipx install omi-cli

# או דרך pip
pip install omi-cli
```

> **חשוב: שם החבילה ושם הפקודה שונים.**
> * החבילה שמתקינים היא **`omi-cli`** (החבילה הנפרדת `omi` היא פרויקט אחר, לא קשור).
> * אחרי ההתקנה מריצים את הפקודה **`omi`**.

מוודאים שההתקנה הצליחה:

```bash
omi --version
omi --help
```

---

## 2. התחברות

`omi-cli` תומך בשני אופני התחברות.

| אופן | מתי מתאים | פקודה |
| :--- | :--- | :--- |
| **מפתח מפתחים (`omi_dev_*`)** | CI/CD, סקריפטים, סוכני AI | `omi auth login --api-key ...` או משתנה סביבה |
| **התחברות דרך הדפדפן (Google/Apple)** | עבודה על המחשב האישי | `omi auth login --browser` |

### התחברות אינטראקטיבית

בלי דגלים, הפקודה תשאל בעצמה באיזה אופן להתחבר:

```bash
omi auth login
# 1) Browser — התחברות דרך Google או Apple (נוח לאדם)
# 2) API key — הדבקת מפתח מפתחים מ-app.omi.me (נוח לסוכנים ול-CI)
```

כשבוחרים מפתח, הקלט מוסתר, ולכן המפתח לא נשאר בהיסטוריית הטרמינל.

### ישירות דרך הדפדפן

```bash
omi auth login --browser
```

### בעזרת מפתח מפתחים

את המפתח מקבלים ב-[app.omi.me](https://app.omi.me) תחת **Developer → API Keys**.

```bash
# שמירת המפתח בקונפיגורציה
omi auth login --api-key omi_dev_...

# או להעביר דרך הסביבה — עדיף ל-CI/CD ולקונטיינרים
export OMI_API_KEY=omi_dev_...
```

משתנה `OMI_API_KEY` משמש כשלפרופיל הפעיל אין מפתח שמור,
ולכן בקונטיינר לא צריך לכתוב דבר לדיסק. אם בפרופיל כבר שמור מפתח,
יש לו עדיפות על משתנה הסביבה.

### בדיקת ההתחברות

שתי פקודות עונות על שאלות שונות, ולא כדאי לבלבל ביניהן:

* `omi auth status` — מה שמור **מקומית**: פרופיל, מפתח מוסתר, תוקף.
  עובד בלי רשת.
* `omi auth whoami` — פנייה **לשרת של Omi**: בודק שהמפתח באמת
  מתקבל. דורש רשת.

```bash
omi auth status    # בדיקה מקומית, אופליין
omi auth whoami    # בדיקה מול השרת
```

רענון סשן OAuth שתוקפו מתקרב לסוף בלי התחברות מחדש — רלוונטי רק להתחברות דרך הדפדפן (OAuth). עבור מפתחות `omi_dev_*` הפקודה אינה מרעננת; החליפו את המפתח באפליקציית ה-web תחת `Developer → API Keys`:

```bash
omi auth refresh
```

התנתקות:

```bash
omi auth logout
```

---

## 3. פקודות מרכזיות

### זיכרונות (memories)

עובדות וידע שהמערכת זכרה עליכם.

```bash
# רשימת הזיכרונות
omi memory list

# יצירת זיכרון חדש
omi memory create "המשתמש מעדיף ערכת נושא כהה" --category lifestyle

# צפייה בזיכרון מסוים
omi memory get <MEMORY_ID>
```

### שיחות (conversations)

היסטוריית דיבור וטקסט מהמכשיר או מהאפליקציה.

```bash
# 5 השיחות האחרונות
omi conversation list --limit 5

# שיחה מלאה כולל תמלול
omi conversation get <CONVERSATION_ID> --include-transcript
```

### משימות (action items)

משימות ש-Omi חילץ מהשיחות.

```bash
# רק משימות פתוחות
omi action-item list --open

# סימון משימה כהושלמה
omi action-item complete <ACTION_ITEM_ID>
```

### מטרות (goals)

```bash
# רשימת המטרות
omi goal list

# רישום ערך התקדמות חדש (צריך את שני הארגומנטים: מטרה וערך)
omi goal progress <GOAL_ID> 25

# היסטוריית שינויים
omi goal history <GOAL_ID>
```

---

## שאלה בשפה חופשית (`ask`)

פקודה נפרדת ברמה העליונה: שואלת שאלה בשפה טבעית,
והתשובה נבנית מהשיחות שלכם עצמכם.

```bash
omi ask "מה החלטתי לגבי המעבר"
omi --json ask "אילו משימות הבטחתי לסגור השבוע"
```

---

## 4. JSON וסקריפטים (`--json`)

`omi-cli` יודע להחזיר JSON קריא-מכונה. הדגל `--json` הוא **גלובלי**,
ולכן מציבים אותו **לפני** תת-הפקודה.

```bash
# זיכרונות: שליפת id, תוכן וקטגוריה
omi --json memory list | jq '.[] | {id, content, category}'

# כותרות השיחות האחרונות
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# משימות פתוחות
omi --json action-item list --open | jq '.'
```

> **טעות נפוצה.** `--json` בא לפני תת-הפקודה, לא אחריה.
> * נכון: `omi --json memory list`
> * לא נכון: `omi memory list --json`

במצב `--json` לא יוצא ל-standard output דבר מלבד ה-JSON עצמו —
אפשר לסמוך על זה בסקריפטים.

---

## 5. קודי יציאה

הקודים יציבים, ולכן אפשר להסתעף לפיהם בסקריפטים וב-CI.

| קוד | משמעות | מתי מתרחש |
| :---: | :--- | :--- |
| `0` | הצלחה | הפקודה הושלמה |
| `1` | שגיאת קריאה | ולידציה של omi-cli עצמו (למשל `--browser` ו-`--api-key` יחד, בחירה לא חוקית, קלט ריק) |
| `2` | שגיאת גישה או ארגומנטים | לא מחובר, מפתח שגוי או שפג תוקפו — וגם שגיאות פרסר (דגל לא מוכר, ארגומנט חסר) |
| `3` | שגיאת שרת | תשובת 5xx, timeout, אין תקשורת |
| `4` | יותר מדי בקשות | 429 Too Many Requests |
| `5` | לא נמצא | 404, המזהה שצוין לא קיים |

דוגמה לבדיקה ב-Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "המפתח עובד"
else
  code=$?
  [ "$code" -eq 2 ] && echo "צריך להתחבר מחדש"
  [ "$code" -eq 3 ] && echo "השרת לא זמין, לנסות מאוחר יותר"
fi
```

---

## 6. משתני סביבה

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_המפתח_שלכם"

omi --json memory list --limit 10
```

כדי שהמפתח ייטען גם בסשנים חדשים, מוסיפים את השורה ל-`~/.bashrc` או `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_המפתח_שלכם"

# פירוק JSON עם PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

הגדרה קבועה:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_המפתח_שלכם", "User")
```

---

## 7. אפליקציית Omi Desktop מקומית

אם אפליקציית הדסקטופ של Omi רצה, חלק מהנתונים זמין ישירות,
בלי לעבור דרך הענן.

```bash
# הגדרת כתובת ה-API המקומי
omi local configure --url http://127.0.0.1:47778 --token הטוקן_שלכם

# בדיקה שהוא עונה
omi --json local status

# חיפוש בהיסטוריית המסך
omi --json local search-screen "תעריפים" --days 7 --app Safari

# צילום מסך לפי מזהה
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# שאילתת SQL חופשית על בסיס הנתונים המקומי
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

סדר העבודה: קודם `local status`, אחר כך `local tools` — כדי לגלות את
הכלים הזמינים והפרמטרים שלהם — ורק אז קריאות.

---

## 8. פרופילים

אם יש כמה חשבונות או סביבות, מפרידים ביניהם עם פרופילים.
ההגדרות נשמרות ב-`~/.omi/config.toml`.

```bash
# התחברות לפרופיל האישי
omi --profile personal auth login

# התחברות לפרופיל העבודה
omi --profile work auth login

# הרצת פקודה בפרופיל מסוים
omi --profile work memory list
```

אם לא מציינים פרופיל, ה-CLI משתמש קודם בפרופיל ממשתנה הסביבה `OMI_PROFILE`, אז בפרופיל הפעיל מקובץ ההגדרות, ואז ב-`default`. סדר הקדימות: `--profile`, אחר כך `OMI_PROFILE`, אחר כך הפרופיל הפעיל ב-`~/.omi/config.toml`, ואז `default`.

צפייה בשינוי הקונפיגורציה עצמה:

```bash
# מה מוגדר כרגע
omi config show

# איפה נמצא קובץ הקונפיגורציה
omi config path

# שינוי ערך
omi config set api_base https://api.omi.me
```

---

## 9. מה הלאה

* [`agent_quickstart.md`](./agent_quickstart.md) — איך לחבר את `omi-cli` לסוכן AI.
* [`shell_examples.sh`](./shell_examples.sh) — דוגמאות shell מוכנות.
* [תיעוד Omi](https://docs.omi.me/doc/developer/cli/introduction) — חומר הייחוס המלא לפקודות.
