# omi-cli अभिकर्त्रृभ्यः

> LLM-चालित-यन्त्रेभ्यः व्यावहारिक-मार्गदर्शिका (Claude Code, Cursor, भवतां स्वकीयाः बॉट्-प्रणाल्यः)।

## CLI किमर्थम् अभिकर्त्रृ-अनुकूलम् अस्ति

* **स्थिर-JSON-अनुबन्धः।** `--json` विकल्पः stdout-मध्ये केवलम् एकं मान्यं JSON-प्रलेखं
  उत्पादयति — प्रगतिसन्देशाः, चक्राणि वा न भवन्ति। दोषाः stderr-मध्ये
  `{"error": "...", "detail": "..."}` रूपेण प्रेष्यन्ते।
* **स्थिर-निर्गमन-सङ्केताः।** `0` सफलं / `1` उपयोगः / `2` प्रमाणीकरणम् / `3` सर्वर् / `4` दर-सीमा
  / `5` न प्राप्तम्। अभिकर्तारः प्राकृतभाषादोषाणां विश्लेषणं विना एतेषां आधारेण शाखान्वयं
  कर्तुं शक्नुवन्ति।
* **शिरोहीन-सन्दर्भेषु संवादात्मक-प्रश्नाः न भवन्ति।** विनाशकारी-आज्ञाभ्यः `--yes` (अथवा `-y`)
  योजयतु; संवादात्मकप्रवेशस्य लङ्घनाय `--api-key` प्रयोजयतु अथवा `OMI_API_KEY` निर्धारयतु।
* **क्षमाशीला पुनरावृत्ति-प्रक्रिया।** `429` तथा `5xx` दोषाः प्रकटीकरणात् पूर्वं
  घाताङ्कीय-विरामेन सह पुनः प्रयास्यन्ते।

## प्रमाणीकरणम् (सकृत्, मानवेन)

प्रयोक्ता Omi जालानुपयोगतः (`https://app.omi.me` → Developer → API Keys)
विकासक-API-कुञ्चिकां प्राप्नोति, ततः परं च:

```bash
omi auth login                          # संवादात्मक-लेपनम्; कुञ्चिका शैल-इतिहासे न तिष्ठति
# अथवा
export OMI_API_KEY=omi_dev_...          # क्षणिकम्, पात्र-अनुकूलम् (container-friendly)
```

## पञ्च प्रमुख-कार्याणि यानि अभिकर्तारः बहुधा कुर्वन्ति

### १. स्मृतीः पठतु

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### २. नूतनां स्मृतिं रचयतु

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### ३. सम्भाषणाणि पठतु

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### ४. उद्घाटितानि कार्यसूच्यङ्गानि पठतु

```bash
omi action-item list --json --open
```

### ५. कार्यसूच्यङ्गं सम्पन्नम् इति चिह्नीकरोतु

```bash
omi action-item complete --json a1b2c3d4
```

## स्थानीय-डेस्कटॉप-API

यदा Omi Desktop स्वकीयं स्थानीय-API प्रकाशयति, तदा अभिकर्तारः क्लाउड-विकासक-API
विना यन्त्रस्थ-पटल-इतिहासम्, संक्षेपाणि, SQL, कार्याणि च पृच्छितुं शक्नुवन्ति:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# अथवा, क्षणिक-सत्रार्थम्:
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

केवलं तदैव कार्याणि सम्पादयतु वा विलोपयतु यदा प्रयोक्ता स्पष्टं प्रार्थयति:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

`omi local screenshot SCREENSHOT_ID --output PATH` आज्ञा पटलप्रतिबिम्बं डिस्क-मध्ये
लिखति, स्क्रिप्ट्-कृते च stdout-मध्ये JSON मुद्रयति। प्रतिबिम्ब-ID प्रायः `local search-screen`
तः अथवा `screenshots` सारण्याः उपरि SQL-तः आगच्छति। यदि Desktop `screenshot_pending`,
`screenshot_file_missing`, अथवा `screenshot_chunk_corrupted` सदृशं संरचित-दोषं ददाति,
तर्हि JSON-विधिः stderr-मध्ये `reason`, `hint`, तथा `screenshot_id` क्षेत्राणि रक्षति येन
अभिकर्तारः पुरातन-ID पुनः प्रयोक्तुं शक्नुवन्ति वा यथार्थ-प्रतिबन्धं सूचयितुं शक्नुवन्ति।
दृष्टि-साधनेभ्यः प्रेषणात् पूर्वं `file PATH` द्वारा सफलोत्पादानां प्रमाणीकरणं कुर्वन्तु।

## व्यावहारिकम् उदाहरणम्: पायथन्-अभिकर्त्रृ-चक्रम्

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """JSON-विधौ omi CLI चालयतु, असफलेषु निर्गमनसङ्केतेषु दोषं जनयतु च।"""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # CLI JSON-विधौ stderr-मध्ये संरचित-दोषान् मुद्रयति:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# सर्वाणि उद्घाटितानि कार्याणि पठित्वा ३० दिनेभ्यः पुरातनं सर्वं पूर्णं चिह्नीकरोतु।
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## दर-सीमा-नियन्त्रणम्

स्मृतयः: 120/घण्टा। सम्भाषणाणि: 25/घण्टा। समूह-रचनाः: 15/घण्टा।

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # दर-सीमा प्राप्ता
    err = json.loads(result.stderr)
    # err["detail"] दृश्यते: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## उपायाः

* यदि भवतः अभिकर्ता एकाधिकान् Omi-खातान् प्रबन्धयति तर्हि `--profile <नाम>` उपयुज्यताम्।
  प्रत्येक-रूपरेखायाः स्वकीया प्रमाणीकरण-सूचना तथा API-आधारः अस्ति।
* स्थानीय-पृष्ठभाग-परीक्षणार्थं `--api-base http://localhost:8080` उपयुज्यताम्।
* एकस्मिन् धावने Desktop API-विन्यासानां अतिक्रमाय `OMI_LOCAL_API_URL` तथा `OMI_LOCAL_TOKEN`
  प्रयुज्यताम्।
* दोषनिवारणाय `--verbose` उपयुज्यताम् — एतत् stdout अप्रभावितं कृत्वा stderr-मध्ये
  `METHOD path → status (Ns)` अभिलेखयति, येन JSON-विधिः सिद्धा तिष्ठति।
* सम्भाषणे सामग्रीं प्रेषयितुं (pipe), `--text -` उपयुज्यताम्:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
