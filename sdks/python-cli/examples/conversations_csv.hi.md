# conversation सूची एक्सपोर्ट को CSV में बदलें

इस रेसिपी से conversation मेटाडेटा को स्प्रेडशीट में देख सकते हैं। यह
सहेजी गई JSON एक्सपोर्ट फ़ाइल पढ़ता है, कोई नेटवर्क अनुरोध नहीं करता, और
ट्रांसक्रिप्ट एक्सपोर्ट नहीं करता। शुरुआती एक्सपोर्ट के लिए आपको Python 3.10+
और प्रमाणित `omi-cli` चाहिए।

अधिकतम 200 conversations एक्सपोर्ट करें:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

फ़ाइल बदलने से पहले जांच लें कि कमांड सफल रही। यह एक पेज है,
पूरे अकाउंट का बैकअप नहीं। अगला पेज लाने के लिए `--offset` को
200 बढ़ाएं और दूसरा फ़ाइल नाम इस्तेमाल करें। अनुरोधों के बीच अकाउंट में
बदलाव offset pagination को प्रभावित कर सकते हैं; यह रेसिपी एक सुसंगत
स्नैपशॉट का वादा नहीं करती।

नीचे दिया कोड `conversations_to_csv.py` नाम से सहेजें:

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

कनवर्टर चलाएं:

```sh
python conversations_to_csv.py conversations.json conversations.csv
```

नतीजे को Excel या किसी अन्य स्प्रेडशीट ऐप में UTF-8, comma-delimited टेक्स्ट
के रूप में इम्पोर्ट करें। कनवर्टर पूरे ID, एक्सेंट वाले अक्षर, उद्धृत
टेक्स्ट और एम्बेडेड नई लाइनें सुरक्षित रखता है। खाली फ़ील्ड खाली सेल बनते हैं;
खाली सूची पर सिर्फ़ कॉलम हेडर बनता है। यह मौजूदा डेस्टिनेशन फ़ाइल को ओवरराइट
करने से मना करता है, और असफल लेखन पर कोई अधूरी फ़ाइल नहीं छोड़ता। एक्सपोर्ट
की गई फ़ाइल को निजी conversation डेटा मानें। बिना बदले हुए सटीक
मानों के लिए मूल JSON सहेजकर रखें; CSV सामान्य formula-जैसे मानों के सामने
एक apostrophe जोड़ता है ताकि उनका इच्छित टेक्स्ट अर्थ स्पष्ट रहे।
