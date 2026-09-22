# تحويل تصدير قائمة المحادثات إلى قاعدة بيانات SQLite

استخدم هذه الوصفة عندما ترغب في الاستعلام عن محادثات Omi باستخدام لغة SQL — للتصفية حسب الفئة، أو البحث في العناوين، أو الربط مع عناصر المهام (action-items). يقرأ هذا السكربت ملف تصدير JSON واحداً أو أكثر، ولا يقوم بأي طلبات عبر الشبكة، ويكمل دليلي [`conversations_csv.md`](conversations_csv.md) و [`conversations_xlsx.md`](conversations_xlsx.md).

تحتاج إلى بايثون 3.10+ (`Python 3.10+`) وواجهة سطر أوامر `omi-cli` مصادق عليها لإجراء التصدير الأولي. تتطلب أمثلة صدفة `python -m sqlite3` التفاعلية أدناه إصدار بايثون 3.12+.

تصدير ما يصل إلى 200 محادثة:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

تحقق من نجاح الأمر قبل الاستيراد. هذه صفحة واحدة وليست نسخة احتياطية كاملة للحساب. لاسترداد صفحة أخرى، قم بزيادة `--offset` بمقدار 200 واستخدم اسماً مختلفاً للملف. التغييرات التي تطرأ على الحساب بين الطلبات قد تؤثر على ترقيم الصفحات عبر الإزاحة (offset pagination)؛ لا تضمن هذه الوصفة لقطة متسقة للحالة.

شغّل أداة الاستيراد:

```sh
python sdks/python-cli/examples/conversations_to_sqlite.py conversations.json -o conversations.db
```

يمكن دمج صفحات متعددة في عملية تشغيل واحدة:

```sh
python sdks/python-cli/examples/conversations_to_sqlite.py \
  page1.json page2.json page3.json -o conversations.db
```

إعادة التشغيل باستخدام نفس التصديرات أو تصديرات محدثة آمنة تماماً: تستخدم أداة الاستيراد `INSERT OR REPLACE` بالاعتماد على المفتاح الأساسي `id`، بحيث يتم تحديث الصفوف بدلاً من تكرارها.

## مخطط قاعدة البيانات (Schema)

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    category      TEXT,
    source        TEXT,
    started_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    created_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    updated_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    transcript    TEXT,
    raw_json      TEXT NOT NULL
);
```

تتم تسوية جميع الطوابع الزمنية إلى نص بتوقيت UTC بصيغة `YYYY-MM-DD HH:MM:SS` حتى تعمل دوال التاريخ والوقت في SQLite (`strftime` و `julianday` و `date`) دون الحاجة إلى تحويل نوع البيانات. يتم الاحتفاظ بالسجل الأصلي حرفياً في حقل `raw_json` لاستعلامات `json_extract`.

## أمثلة على الاستعلامات

```sh
python -m sqlite3 conversations.db
```

حساب عدد المحادثات حسب الفئة:

```sql
SELECT category, COUNT(*) AS n
FROM conversations
GROUP BY category
ORDER BY n DESC;
```

العثور على المحادثات من آخر 7 أيام:

```sql
SELECT title, started_at
FROM conversations
WHERE started_at >= date('now', '-7 days')
ORDER BY started_at DESC;
```

استخراج حقل متداخل من الـ JSON الخام (مثل الرمز التعبيري emoji):

```sql
SELECT title, json_extract(raw_json, '$.structured.emoji') AS emoji
FROM conversations
LIMIT 10;
```

البحث في العناوين:

```sql
SELECT id, title, category, started_at
FROM conversations
WHERE title LIKE '%meeting%'
ORDER BY started_at DESC;
```

تعامل مع الملف المُصدَّر كبيانات محادثة خاصة. تحتوي قاعدة بيانات SQLite على نفس المعلومات الموجودة في ملف JSON المصدر. للحصول على القيم الدقيقة غير المعدلة، احتفظ بملف JSON المصدر إلى جانب قاعدة البيانات.
