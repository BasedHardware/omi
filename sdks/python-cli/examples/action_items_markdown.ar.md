# تصدير عناصر عمل Omi إلى Markdown (لتطبيقات Obsidian / Notion / Second Brain)

استخدم هذا الدليل لتصدير ومزامنة عناصر العمل (Action Items) الملتقطة بواسطة جهاز Omi القابل للارتداء إلى قوائم مهام Markdown نظيفة وتفاعلية. تتضمن الملفات الناتجة ترويسة YAML frontmatter، ومربعات اختيار مهام قياسية بتنسيق GFM (`- [ ]` و `- [x]`)، وتواريخ الاستحقاق، وروابط العودة إلى المحادثات الأصلية، وجاهزة للاستخدام المباشر في **Obsidian** أو **Notion** أو **Logseq** أو خزائن المهام الشخصية.

---

## المتطلبات الأساسية

تأكد من تثبيت واجهة سطر الأوامر `omi` والمصادقة عليها:

```sh
pip install omi-cli
omi auth login
```

تحقق من قدرتك على سرد عناصر العمل الخاصة بك:

```sh
omi action-item list
```

---

## البدء السريع

### 1. التصدير المباشر عبر التمرير (Stdout)

توليد Markdown مباشرة من تيار مخرجات CLI:

```sh
omi --json action-item list | python action_items_to_markdown.py -
```

### 2. التصدير إلى ملف مهام مخصص

تصدير مهامك إلى ملاحظة Markdown واحدة (مثال: لخزينة Obsidian أو استيراد Notion):

```sh
omi --json action-item list | python action_items_to_markdown.py - --output ~/vault/Tasks.md
```

### 3. التصفية بحسب الحالة (المهام المعلقة فقط)

تصدير عناصر العمل المفتوحة والمعلقة فقط:

```sh
omi --json action-item list --open | python action_items_to_markdown.py - --status open --output ~/vault/PendingTasks.md
```

### 4. التجميع بحسب تاريخ الاستحقاق في ملاحظات يومية

تقسيم عناصر العمل إلى ملاحظات يومية منفصلة في مجلد:

```sh
python action_items_to_markdown.py action_items.json --output-dir ./vault/daily-tasks/ --group-by date
```

---

## خيارات سطر الأوامر (CLI Options)

| الخيار | الراية (Flag) | الوصف | القيمة الافتراضية |
| :--- | :--- | :--- | :--- |
| `input` | الموضع 1 | مسار ملف JSON، أو `-` للقراءة من stdin | *(مطلوب)* |
| `--output` | `-o` | مسار ملف الإخراج (يكتب جميع العناصر إلى هذا الملف) | `stdout` |
| `--output-dir` | `-d` | مجلد الإخراج لكتابة ملفات Markdown | `None` |
| `--status` | `--status` | تصفية العناصر: `all` أو `open` أو `completed` | `all` |
| `--group-by` | `--group-by` | استراتيجية التجميع: `status` أو `date` أو `none` | `status` |
| `--title` | `--title` | عنوان ترويسة مخصص للملاحظة | `"Omi Action Items"` |

---

## هيكل المخرجات

### نموذج لملاحظة مُصدَّرة (`Tasks.md`)

```markdown
---
type: action-items
total: 3
open: 2
completed: 1
exported_at: "2026-09-14T15:00:00+00:00"
tags:
  - omi
  - action-items
  - tasks
---

# Omi Action Items

> **Summary:** 2 open, 1 completed (3 total). Exported from Omi CLI.

## 📌 Pending Tasks

- [ ] Email quarterly financial update to investment team
  *(📅 Due: 2026-09-15 18:00 UTC · 🔗 [[conversation_a1b2c3d4]] · `#act_99182`)*
- [ ] Review pull request for memory sync latency optimization
  *(🔗 [[conversation_e5f6g7h8]] · `#act_99183`)*

## ✅ Completed Tasks

- [x] Configure Luno exchange sell limit order for portfolio rebalancing
  *(📅 Due: 2026-09-14 05:30 UTC · `#act_99180`)*
```

---

## مسارات عمل التكامل

### مزامنة صندوق الوارد في خزينة Obsidian

أضف هذا السطر إلى سكربت بدء التشغيل اليومي أو مهمة cron لإلحاق عناصر العمل الجديدة تلقائياً بصندوق الوارد في Obsidian:

```sh
omi --json action-item list --open | python action_items_to_markdown.py - --status open --output ~/Documents/Obsidian/Inbox/OmiTasks.md
```

### استيراد Notion

1. شغّل:
   ```sh
   omi --json action-item list | python action_items_to_markdown.py - --output omi_tasks.md
   ```
2. في Notion، افتح أي صفحة، انقر على **Import** في الشريط الجانبي أو القائمة، اختر **Markdown & CSV**، وحدد `omi_tasks.md`. سيقوم Notion تلقائياً بتحويل مربعات الاختيار إلى عناصر مهام تفاعلية (To-Do items).

---

## مبادئ التصميم

- **صفر مكتبات خارجية:** يستخدم وحدات المكتبة القياسية للغة بايثون فقط (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`).
- **آمن ومرن:** يتعامل تلقائياً مع ترميز UTF-8 مع علامة ترتيب البايت (BOM) الشائعة في Windows PowerShell.
- **حماية من تجاوز المسار:** يعقم جميع مكونات التاريخ والعنوان ضد هجمات تجاوز المسار (path traversal).
- **جاهز للدماغ الثاني (Second Brain):** يستخدم ترويسة YAML قياسية تدعمها تطبيقات Obsidian Dataview و Logseq و Notion.
