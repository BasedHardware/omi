# تحويل تصدير قائمة المحادثات إلى CSV

استخدم هذه الوصفة لمراجعة البيانات الوصفية للمحادثات في جدول بيانات (Spreadsheet). يقرأ هذا السكربت ملف تصدير JSON محفوظاً، ولا يقوم بأي طلبات عبر الشبكة، ولا يصدّر النصوص الكاملة للمحادثات. تحتاج إلى بايثون 3.10+ (`Python 3.10+`) وواجهة سطر أوامر `omi-cli` مصادق عليها لإجراء التصدير الأولي.

تصدير ما يصل إلى 200 محادثة:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

تحقق من نجاح الأمر قبل تحويل الملف. هذه صفحة واحدة وليست نسخة احتياطية كاملة للحساب. لاسترداد صفحة أخرى، قم بزيادة `--offset` بمقدار 200 واستخدم اسماً مختلفاً للملف. التغييرات التي تطرأ على الحساب بين الطلبات قد تؤثر على ترقيم الصفحات عبر الإزاحة (offset pagination)؛ لا تضمن هذه الوصفة لقطة متسقة للحالة.

احفظ ما يلي باسم `conversations_to_csv.py`:

```python
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "title", "category", "started_at", "source")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source, destination):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
        values = (item.get("id"), structured.get("title"), structured.get("category"),
                  item.get("started_at"), item.get("source"))
        rows.append([spreadsheet_text(value) for value in values])
    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")
    output_path = Path(destination)
    # Exclusive creation still protects an existing export.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # Leave no partial export behind when the write itself fails.
        output_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python conversations_to_csv.py INPUT.json OUTPUT.csv")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
```

شغّل أداة التحويل:

```sh
python conversations_to_csv.py conversations.json conversations.csv
```

استورد النتيجة كنص مفصول بفواصل بترميز UTF-8 في Excel أو أي تطبيق جداول بيانات آخر. تحافظ أداة التحويل على المعرفات الكاملة، الحروف الخاصة، النصوص المقتبسة، والأسطر الجديدة المضمنة. تصبح الحقول المفقودة خلايا فارغة؛ والقائمة الفارغة تُنتج ترويسة الأعمدة فقط. ترفض الأداة الكتابة فوق ملف موجود، كما أن أي فشل في الكتابة لا يترك ملفاً جزئياً خلفه. تعامل مع الملف المُصدَّر كبيانات محادثة خاصة. للحصول على القيم الدقيقة غير المعدلة، احتفظ بملف JSON المصدر؛ يضيف ملف CSV علامة اقتباس أحادية إلى القيم الشبيهة بالصيغ لجعل تفسيرها النصي مقصوداً وصريحاً.
