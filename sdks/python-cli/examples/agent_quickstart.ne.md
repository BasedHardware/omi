# एजेन्टहरूका लागि omi-cli

> LLM-सञ्चालित प्रणालीहरू (Claude Code, Cursor, तपाईंका आफ्ना बटहरू) का लागि व्यावहारिक मार्गदर्शिका।

## CLI किन एजेन्ट-अनुकूल छ

* **स्थिर JSON सम्झौता।** `--json` ले stdout मा एउटा वैध JSON कागजात र
  *केवल* JSON कागजात मात्र उत्सर्जन गर्दछ — कुनै प्रगति सन्देश वा स्पिनरहरू हुँदैनन्। त्रुटिहरू
  stderr मा `{"error": "...", "detail": "..."}` को रूपमा जान्छन्।
* **स्थिर निकास कोडहरू (Exit Codes)।** `0` ठीक / `1` प्रयोग / `2` प्रमाणीकरण / `3` सर्भर / `4` दर
  सीमित / `5` फेला परेन। एजेन्टहरूले प्राकृतिक-भाषाका त्रुटिहरू पार्स नगरीकन यी आधारमा शाखा
  विभाजन गर्न सक्छन्।
* **हेडलेस (headless) सन्दर्भहरूमा कुनै अन्तर्क्रियात्मक प्रम्प्टहरू हुँदैनन्।** विनाशकारी
  कमाण्डहरूमा `--yes` (वा `-y`) पास गर्नुहोस्; अन्तर्क्रियात्मक लगइन छोड्न `--api-key` पास गर्नुहोस्
  वा `OMI_API_KEY` सेट गर्नुहोस्।
* **क्षमाशील पुन: प्रयास व्यवहार।** `429` र `5xx` देखा पर्नु अघि ब्याकअफका साथ
  पुन: प्रयास गरिन्छ।

## प्रमाणीकरण (एक पटक, मानवद्वारा)

प्रयोगकर्ताले Omi वेब एप (`https://app.omi.me` → Developer → API Keys) बाट
डेभलपर API कुञ्जी प्राप्त गर्छ र निम्न मध्ये एक गर्छ:

```bash
omi auth login                          # अन्तर्क्रियात्मक पेस्ट; कुञ्जी शेल इतिहासमा रहँदैन
# वा
export OMI_API_KEY=omi_dev_...          # अल्पकालीन, कन्टेनर-अनुकूल
```

## एजेन्टहरूले प्रायः गर्ने पाँच कुराहरू

### १. सम्झनाहरू पढ्ने

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### २. सम्झना सिर्जना गर्ने

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### ३. कुराकानीहरू पढ्ने

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ४. खुला कार्यहरू पढ्ने

```bash
omi action-item list --json --open
```

### ५. कार्य सम्पन्न भएको चिन्ह लगाउने

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय डेस्कटप API

जब Omi Desktop ले आफ्नो स्थानीय API उपलब्ध गराउँछ, एजेन्टहरूले क्लाउड डेभलपर API
प्रयोग नगरीकनै उपकरणमै स्क्रिन इतिहास, रिक्यापहरू, SQL, र कार्यहरू सोधपुछ गर्न सक्छन्:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# वा, अल्पकालीन सत्रहरूका लागि:
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

प्रयोगकर्ताले स्पष्ट रूपमा सोधेमा मात्र कार्यहरू सम्पन्न वा मेटाउने गर्नुहोस्:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` ले स्क्रिनसटलाई डिस्कमा लेख्छ
र स्क्रिप्टहरूका लागि stdout मा JSON प्रिन्ट गर्छ। स्क्रिनसट आईडी सामान्यतया
`local search-screen` वा `screenshots` तालिकामाथि SQL बाट आउँछ। यदि Desktop ले
`screenshot_pending`, `screenshot_file_missing`, वा `screenshot_chunk_corrupted`
जस्ता संरचित विफलता फिर्ता गर्छ भने, JSON मोडले stderr मा `reason`, `hint`, र
`screenshot_id` क्षेत्रहरू सुरक्षित राख्छ ताकि एजेन्टहरूले पुरानो आईडी पुन: प्रयास गर्न
वा ठ्याक्कै अवरोधक रिपोर्ट गर्न सकून्। भिजन उपकरणहरूमा पठाउनु अघि `file PATH` मार्फत
सफल आउटपुटहरू प्रमाणित गर्नुहोस्।

## व्यावहारिक उदाहरण: पाइथन एजेन्ट लूप

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON मोडमा omi CLI आह्वान गर्नुहोस्, गैर-सफल निकास कोडहरूमा त्रुटि उठाउँदै।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI ले JSON मोडमा stderr मा संरचित त्रुटिहरू प्रिन्ट गर्छ:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सबै खुला कार्यहरू पढ्नुहोस् र ३० दिनभन्दा पुरानालाई सम्पन्न चिन्ह लगाउनुहोस्।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर सीमाहरू व्यवस्थापन गर्ने

सम्झनाहरू: १२०/घण्टा। कुराकानीहरू: २५/घण्टा। ब्याच सिर्जना: १५/घण्टा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर सीमित
    err = json.loads(result.stderr)
    # err["detail"] यस्तो देखिन्छ: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## सुझावहरू

* यदि तपाईंको एजेन्टले धेरै Omi खाताहरू व्यवस्थापन गर्छ भने `--profile <नाम>` प्रयोग गर्नुहोस्।
  प्रत्येक प्रोफाइलको आफ्नै प्रमाण र API आधार हुन्छ।
* स्थानीय ब्याकइन्ड परीक्षणका लागि `--api-base http://localhost:8080` प्रयोग गर्नुहोस्।
* एक पटकको रनका लागि प्रोफाइल-स्थानीय डेस्कटप API सेटिङहरू ओभरराइड गर्न `OMI_LOCAL_API_URL`
  र `OMI_LOCAL_TOKEN` प्रयोग गर्नुहोस्।
* डिबगिङका लागि `--verbose` प्रयोग गर्नुहोस् — यसले stdout लाई असर नगरीकनै stderr मा
  `METHOD path → status (Ns)` लग गर्छ, जसले गर्दा JSON मोड मान्य रहन्छ।
* कुराकानीमा सामग्री पाइप गर्नका लागि, `--text -` प्रयोग गर्नुहोस्:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
