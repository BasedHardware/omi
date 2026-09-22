# تصدير ذكريات ومعلومات Omi إلى Markdown (لتطبيقات Obsidian / Notion / Second Brain)

استخدم هذا الدليل لتصدير ومزامنة الحقائق، والدروس المستفادة، والرؤى، والذكريات الملتقطة بواسطة جهاز Omi القابل للارتداء إلى ملاحظات Markdown مهيكلة. تتميز الملاحظات الناتجة بترويسة YAML frontmatter نظيفة، وتجميع بالرموز التعبيرية بحسب الفئات، ووسوم Obsidian (`#work` و `#skills` وغيرها)، وتواريخ الإنشاء، ومؤشرات الخصوصية، ومحسنة للاستخدام المباشر في **Obsidian** أو **Notion** أو **Logseq** أو الرسوم البيانية للمعرفة الشخصية.

---

## المتطلبات الأساسية

تأكد من تثبيت واجهة سطر الأوامر `omi` والمصادقة عليها:

```sh
pip install omi-cli
omi auth login
```

تحقق من قدرتك على سرد ذكرياتك:

```sh
omi memory list
```

---

## البدء السريع

### 1. التصدير المباشر عبر التمرير (Stdout)

توليد Markdown مباشرة من تيار مخرجات CLI (باستخدام `--limit 200` لالتقاط الحد الأقصى للصفحة الواحدة):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py -
```

### 2. التصدير إلى ملاحظة مخصصة في الخزينة

تصدير الذكريات الحديثة إلى ملاحظة Markdown مهيكلة واحدة (مثال: لخزينة Obsidian أو استيراد Notion):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/vault/Memories.md
```

> **ملاحظة حول ترقيم الصفحات (Pagination):** القيمة الافتراضية لأمر `omi memory list` هي `--limit 25` وتقبل حتى `--limit 200`. للخزائن التي تحتوي على أكثر من 200 ذكرى، استخدم خيار الإزاحة `--offset` (مثال: `--limit 200 --offset 200`) وقم بتمرير أو دمج المخرجات.

### 3. التصفية بحسب الفئة (العمل والتعلم فقط)

تصدير فئات محددة فقط من الذكريات باستخدام تصفية جانب الخادم في CLI:

```sh
omi --json memory list --limit 200 --categories work,learnings | python memories_to_markdown.py - --output ~/vault/WorkMemories.md
```

*(ملاحظة: يوفر السكربت أيضاً خيار `--category` على جانب العميل لتصفية ملفات JSON المُصدَّرة مسبقاً، مثل `python memories_to_markdown.py memories.json --category work,learnings`)*

### 4. التجميع بحسب الفئة في ملاحظات منفصلة

تقسيم الذكريات إلى ملاحظات فئات منفصلة في مجلد محدد:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category
```

يؤدي هذا إلى إنشاء ملفات مثل `work_memories.md` و `skills_memories.md` و `learnings_memories.md` وغيرها.

### 5. التجميع بحسب التاريخ في ملاحظات يومية

تقسيم الذكريات إلى سجلات يومية:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/daily/ --group-by date
```

---

## خيارات سطر الأوامر (CLI Options)

| الخيار | الراية (Flag) | الوصف | القيمة الافتراضية |
| :--- | :--- | :--- | :--- |
| `input` | الموضع 1 | مسار ملف JSON، أو `-` للقراءة من stdin | *(مطلوب)* |
| `--output` | `-o` | مسار ملف الإخراج (يكتب جميع العناصر إلى هذا الملف) | `stdout` |
| `--output-dir` | `-d` | مجلد الإخراج لكتابة ملفات Markdown المنفصلة | `None` |
| `--category` | `-c` | التصفية بحسب الفئة (مفصولة بفواصل: مثل `work,skills`) | `None` (الكل) |
| `--visibility` | `--visibility` | تصفية العناصر: `all` أو `public` أو `private` | `all` |
| `--group-by` | `-g` | استراتيجية التجميع: `category` أو `date` أو `none` | `category` |
| `--title` | `-t` | عنوان ترويسة مخصص للملاحظة | `"Omi Memories & Knowledge Base"` |

---

## هيكل المخرجات

### نموذج لملاحظة مُصدَّرة (`Memories.md`)

```markdown
---
type: omi-memories
total: 4
categories_count: 3
categories:
  - learnings
  - skills
  - work
exported_at: "2026-09-18T09:30:00+00:00"
tags:
  - omi
  - memories
  - second-brain
  - knowledge-base
---

# Omi Memories & Knowledge Base

> **Summary:** 4 memories across 3 categories. Exported from Omi CLI.

## 💼 Work

- Prefers asynchronous communication for architecture proposals and pull request reviews.
  *(📁 `work` · #management #workflow · 🔒 `private` · 📅 2026-09-15 · `#mem_8192a`)
- Leading the TypeScript SDK integration and CLI tooling initiative for Q4.
  *(📁 `work` · #typescript #devtools · 📅 2026-09-16 · `#mem_8192b`)

## 🎯 Skills

- Proficient in Python standard library tool design, FastAPI backend development, and KiCad S-expression parsers.
  *(📁 `skills` · #python #kicad #fastapi · 📅 2026-09-17 · `#mem_8192c`)

## 🧠 Learnings

- KiCad library table parsers require escaping double quotes in nicknames to avoid S-expression syntax errors.
  *(📁 `learnings` · #electronics #eda · 📅 2026-09-18 · `#mem_8192d`)
```

---

## مسارات عمل التكامل

### مزامنة الرسم البياني المعرفي في خزينة Obsidian

أضف هذا السطر إلى إعدادات الشل اليومية أو سكربت الأتمتة لمزامنة أحدث ذكريات Omi مباشرة في دماغك الثاني على Obsidian:

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/Documents/Obsidian/Vault/OmiMemories.md
```

سيقوم Obsidian تلقائياً بفهرسة الفئات، ووسوم الترويسة، والبيانات الوصفية للاستخدام مع استعلامات **Obsidian Dataview**:

```dataview
TABLE file.mtime AS "Updated"
FROM #memories
WHERE contains(categories, "work")
```

### استيراد قاعدة بيانات Notion

1. تصدير ذكرياتك:
   ```sh
   omi --json memory list --limit 200 | python memories_to_markdown.py - --output omi_memories.md
   ```
2. في Notion، افتح أي صفحة في مساحة العمل، انقر على **Import** في الشريط الجانبي، اختر **Markdown & CSV**، وحدد `omi_memories.md`. سيقوم Notion بتحليل الترويسات والوسوم وكتل الفئات إلى أقسام قاعدة بيانات تفاعلية.

---

## مبادئ التصميم

- **صفر مكتبات خارجية:** تم التطوير باستخدام وحدات المكتبة القياسية للغة بايثون فقط (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **آمن ومرن:** يتعامل تلقائياً مع ترميز UTF-8 مع علامة ترتيب البايت (BOM) الصادرة عن Windows PowerShell أو موجهات الأوامر.
- **حماية من تجاوز المسار:** يعقم جميع أسماء الملفات ومسارات المجلدات ضد هجمات تجاوز المسار باستخدام تعابير نمطية صارمة وفحوصات مسار دقيقة.
- **جاهز للدماغ الثاني (Second Brain):** يولد ترويسة YAML متوافقة ومعتمدة من Obsidian و Logseq و Notion.
