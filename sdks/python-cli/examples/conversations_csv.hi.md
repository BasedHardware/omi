# बातचीत-सूची निर्यात को CSV में बदलें

स्प्रेडशीट में बातचीत मेटाडेटा की समीक्षा के लिए यह रेसिपी उपयोग करें। यह एक
सहेजे गए JSON निर्यात को पढ़ती है, कोई नेटवर्क अनुरोध नहीं करती, और ट्रांसक्रिप्ट
निर्यात नहीं करती। प्रारंभिक निर्यात के लिए Python 3.10+ और प्रमाणित `omi-cli`
चाहिए।

अधिकतम 200 बातचीत निर्यात करें:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

फ़ाइल बदलने से पहले जाँचें कि कमांड सफल रही। यह एक पेज है, पूरे खाते का बैकअप
नहीं। दूसरा पेज लेने के लिए `--offset` को 200 से बढ़ाएँ और अलग फ़ाइल-नाम उपयोग
करें। अनुरोधों के बीच खाते में बदलाव ऑफ़सेट पेजिनेशन को प्रभावित कर सकते हैं;
यह रेसिपी सुसंगत स्नैपशॉट का वादा नहीं करती।

निम्नलिखित को `conversations_to_csv.py` के रूप में सहेजें:

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

कनवर्टर चलाएँ:

```sh
python conversations_to_csv.py conversations.json conversations.csv
```

परिणाम को Excel या किसी अन्य स्प्रेडशीट ऐप में UTF-8, कॉमा-विभाजित टेक्स्ट के
रूप में आयात करें। कनवर्टर पूर्ण ID, एक्सेंट युक्त अक्षर, कोटेड टेक्स्ट और एम्बेडेड न्यूलाइन
बनाए रखता है। अनुपस्थित फ़ील्ड खाली सेल बन जाते हैं; खाली सूची केवल कॉलम हेडर
बनाती है। यह मौजूदा गंतव्य को ओवरराइट करने से मना करती है, और विफल लेखन के बाद
कोई आंशिक फ़ाइल नहीं बचती। निर्यात की गई फ़ाइल को निजी बातचीत डेटा मानें।
बिल्कुल अपरिवर्तित मानों के लिए स्रोत JSON रखें; CSV सामान्य सूत्र-जैसे मानों
में अपॉस्ट्रोफ़ जोड़ता है ताकि उनकी इच्छित टेक्स्व्याख्या स्पष्ट हो।
