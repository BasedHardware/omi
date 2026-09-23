# Omi यादों और नॉलेज को Markdown में एक्सपोर्ट करें (Obsidian / Notion / Second Brain)

इस रेसिपी से अपने Omi wearable डिवाइस द्वारा कैप्चर किए गए तथ्यों, सीखी गई बातों, इनसाइट्स और यादों को स्ट्रक्चर्ड Markdown नोट्स में एक्सपोर्ट और सिंक कर सकते हैं। बने हुए नोट्स में साफ़ YAML frontmatter, कैटेगरी के अनुसार emoji समूह, Obsidian टैग (`#work`, `#skills` आदि), बनने की तारीख़ और private visibility संकेतक होते हैं, जो **Obsidian**, **Notion**, **Logseq** या personal knowledge graph के लिए अनुकूलित हैं।

---

## पूर्वापेक्षाएं

सुनिश्चित करें कि `omi` CLI इंस्टॉल और प्रमाणित है:

```sh
pip install omi-cli
omi auth login
```

जांचें कि आप अपनी यादें देख सकते हैं:

```sh
omi memory list
```

---

## क्विकस्टार्ट

### 1. सीधा पाइपलाइन एक्सपोर्ट (Stdout)

CLI आउटपुट स्ट्रीम से सीधे Markdown बनाएं (एक पेज की अधिकतम सीमा तक पहुंचने के लिए `--limit 200` इस्तेमाल करें):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py -
```

### 2. किसी समर्पित Vault नोट में एक्सपोर्ट

हाल की यादों को एक ही स्ट्रक्चर्ड Markdown नोट में एक्सपोर्ट करें (जैसे Obsidian vault या Notion इम्पोर्ट के लिए):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/vault/Memories.md
```

> **Pagination पर नोट:** `omi memory list` डिफ़ॉल्ट रूप से `--limit 25` लेता है और अधिकतम `--limit 200` स्वीकार करता है। 200 से अधिक यादों वाले vault के लिए `--offset` बैचों में पेजिनेट करें (जैसे `--limit 200 --offset 200`) और आउटपुट को पाइप या मिलाएं।

### 3. कैटेगरी से फ़िल्टर करें (सिर्फ़ Work और Learnings)

CLI के server-side फ़िल्टर से सिर्फ़ चुनिंदा कैटेगरी की यादें एक्सपोर्ट करें:

```sh
omi --json memory list --limit 200 --categories work,learnings | python memories_to_markdown.py - --output ~/vault/WorkMemories.md
```

*(नोट: पहले से एक्सपोर्ट की गई JSON फ़ाइलों को फ़िल्टर करने के लिए स्क्रिप्ट में client-side `--category` फ़्लैग भी है, जैसे `python memories_to_markdown.py memories.json --category work,learnings`)*

### 4. कैटेगरी के अनुसार अलग-अलग नोट्स में बांटें

यादों को तय फ़ोल्डर में कैटेगरी-वार अलग नोट्स में बांटें:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category
```

इससे `work_memories.md`, `skills_memories.md`, `learnings_memories.md` जैसी फ़ाइलें बनती हैं।

### 5. तारीख़ के अनुसार दैनिक नोट्स में बांटें

यादों को दैनिक लॉग में बांटें:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/daily/ --group-by date
```

---

## CLI विकल्प

| विकल्प | फ़्लैग | विवरण | डिफ़ॉल्ट |
| :--- | :--- | :--- | :--- |
| `input` | Position 1 | JSON फ़ाइल का पथ, या stdin के लिए `-` | *(आवश्यक)* |
| `--output` | `-o` | आउटपुट फ़ाइल पथ (सभी आइटम इसी फ़ाइल में लिखता है) | `stdout` |
| `--output-dir` | `-d` | अलग-अलग Markdown फ़ाइलें लिखने की डायरेक्टरी | `None` |
| `--category` | `-c` | कैटेगरी से फ़िल्टर (comma-separated: जैसे `work,skills`) | `None` (सभी) |
| `--visibility` | `--visibility` | आइटम फ़िल्टर: `all`, `public`, या `private` | `all` |
| `--group-by` | `-g` | समूहीकरण रणनीति: `category`, `date`, या `none` | `category` |
| `--title` | `-t` | नोट के लिए कस्टम हेडर शीर्षक | `"Omi Memories & Knowledge Base"` |

---

## आउटपुट संरचना

### नमूना एक्सपोर्टेड नोट (`Memories.md`)

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

## इंटीग्रेशन वर्कफ़्लो

### Obsidian Vault Knowledge Graph सिंक

अपनी नवीनतम Omi यादों को सीधे Obsidian second brain में सिंक करने के लिए यह एक-लाइन कमांड अपनी दैनिक shell स्टार्टअप या ऑटोमेशन स्क्रिप्ट में जोड़ें:

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/Documents/Obsidian/Vault/OmiMemories.md
```

Obsidian कैटेगरी, frontmatter टैग और मेटाडेटा को अपने आप इंडेक्स कर लेगा, जिन्हें **Obsidian Dataview** क्वेरी में इस्तेमाल किया जा सकता है:

```dataview
TABLE file.mtime AS "Updated"
FROM #memories
WHERE contains(categories, "work")
```

### Notion डेटाबेस इम्पोर्ट

1. अपनी यादें एक्सपोर्ट करें:
   ```sh
   omi --json memory list --limit 200 | python memories_to_markdown.py - --output omi_memories.md
   ```
2. Notion में किसी भी workspace पेज पर जाएं, साइडबार में **Import** पर क्लिक करें, **Markdown & CSV** चुनें, और `omi_memories.md` चुनें। Notion हेडर, टैग और कैटेगरी ब्लॉक को इंटरैक्टिव डेटाबेस सेक्शन में बदल देगा।

---

## डिज़ाइन सिद्धांत

- **शून्य थर्ड-पार्टी डिपेंडेंसी:** पूरी तरह Python standard library मॉड्यूल (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`) से बना।
- **सुरक्षित और मज़बूत:** Windows PowerShell या कमांड शेल से आए UTF-8 with BOM (Byte Order Mark) को अपने आप संभालता है।
- **Traversal सुरक्षा:** सख़्त regex और resolution जांचों से सभी फ़ाइल नामों और डायरेक्टरी पथों को traversal हमलों से सुरक्षित करता है।
- **Second Brain के लिए तैयार:** Obsidian, Logseq और Notion द्वारा समर्थित मानक YAML frontmatter बनाता है।
