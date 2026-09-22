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

```bash
omi --json local task complete task_1
```
