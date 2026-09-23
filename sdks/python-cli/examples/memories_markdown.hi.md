# Omi Memories और Knowledge को Markdown में निर्यात करें (Obsidian / Notion / Second Brain)

अपने Omi वेयरेबल डिवाइस में कैप्चर किए गए तथ्य, सीख, अंतर्दृष्टि और यादों को
संरचित Markdown नोट्स में निर्यात और सिंक करने के लिए यह रेसिपी उपयोग करें।
परिणामी नोट्स में साफ़ YAML frontmatter, श्रेणी-विशिष्ट emoji समूह, Obsidian
टैग (`#work`, `#skills` आदि), निर्माण तिथियाँ और निजी दृश्यता संकेतक होते हैं,
जो **Obsidian**, **Notion**, **Logseq**, या व्यक्तिगत knowledge graphs के लिए
अनुकूलित हैं।

---

## आवश्यकताएँ

सुनिश्चित करें कि `omi` CLI इंस्टॉल और प्रमाणित है:

```sh
pip install omi-cli
omi auth login
```

जाँचें कि आप अपनी यादें सूचीबद्ध कर सकते हैं:

```sh
omi memory list
```

---

## Quickstart

### 1. Direct Pipeline Export (Stdout)

CLI आउटपुट स्ट्रीम से सीधे Markdown बनाएँ (एकल-पेज अधिकतम सीमा तक कैप्चर
करने के लिए `--limit 200` का उपयोग):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py -
```

### 2. Export to a Dedicated Vault Note

हाल की यादों को एक संरचित Markdown नोट में निर्यात करें (जैसे, Obsidian vault
या Notion आयात के लिए):

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/vault/Memories.md
```

> **Pagination पर नोट:** `omi memory list` डिफ़ॉल्ट रूप से `--limit 25` लेता है
> और `--limit 200` तक स्वीकार करता है। 200 से अधिक यादों वाले vaults के लिए,
> `--offset` बैच से पेजिनेट करें (जैसे, `--limit 200 --offset 200`) और आउटपुट
> पाइप या संयोजित करें।

### 3. Filter by Category (Work & Learnings Only)

CLI के सर्वर-साइड फ़िल्टर से केवल विशिष्ट श्रेणियों की यादें निर्यात करें:

```sh
omi --json memory list --limit 200 --categories work,learnings | python memories_to_markdown.py - --output ~/vault/WorkMemories.md
```

*(नोट: स्क्रिप्ट पहले से निर्यातित JSON फ़ाइलों के लिए क्लाइंट-साइड `--category`
फ़्लैग भी देती है, जैसे `python memories_to_markdown.py memories.json --category work,learnings`)*

### 4. Group by Category into Separate Notes

यादों को निर्धारित फ़ोल्डर में अलग-अलग श्रेणी नोट्स में विभाजित करें:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category
```

इससे `work_memories.md`, `skills_memories.md`, `learnings_memories.md` आदि
फ़ाइलें बनती हैं।

### 5. Group by Date into Daily Notes

यादों को दैनिक लॉग में विभाजित करें:

```sh
python memories_to_markdown.py memories.json --output-dir ./vault/daily/ --group-by date
```

---

## CLI Options

| Option | Flag | Description | Default |
| :--- | :--- | :--- | :--- |
| `input` | Position 1 | Path to JSON file, or `-` for stdin | *(Required)* |
| `--output` | `-o` | Output file path (writes all items to this file) | `stdout` |
| `--output-dir` | `-d` | Output directory to write separated Markdown files | `None` |
| `--category` | `-c` | Filter by category (comma-separated: e.g. `work,skills`) | `None` (all) |
| `--visibility` | `--visibility` | Filter items: `all`, `public`, or `private` | `all` |
| `--group-by` | `-g` | Grouping strategy: `category`, `date`, or `none` | `category` |
| `--title` | `-t` | Custom header title for the note | `"Omi Memories & Knowledge Base"` |

---

## Output Structure

### Sample Exported Note (`Memories.md`)

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

## Integration Workflows

### Obsidian Vault Knowledge Graph Sync

अपनी दैनिक shell शुरुआत या automation स्क्रिप्ट में यह one-liner जोड़ें ताकि
नवीनतम Omi यादें सीधे आपके Obsidian second brain में सिंक हों:

```sh
omi --json memory list --limit 200 | python memories_to_markdown.py - --output ~/Documents/Obsidian/Vault/OmiMemories.md
```

Obsidian स्वचालित रूप से श्रेणियों, frontmatter टैग और मेटाडेटा को अनुक्रमित
करेगा ताकि **Obsidian Dataview** क्वेरी के साथ उपयोग हो सके:

```dataview
TABLE file.mtime AS "Updated"
FROM #memories
WHERE contains(categories, "work")
```

### Notion Database Import

1. अपनी यादें निर्यात करें:
   ```sh
   omi --json memory list --limit 200 | python memories_to_markdown.py - --output omi_memories.md
   ```
2. Notion में कोई भी workspace पेज खोलें, साइडबार में **Import** पर क्लिक करें,
   **Markdown & CSV** चुनें, और `omi_memories.md` चुनें। Notion हेडर, टैग और
   श्रेणी ब्लॉक को इंटरैक्टिव डेटाबेस अनुभागों में parse करेगा।

---

## Design Principles

- **Zero Third-Party Dependencies:** केवल Python standard library modules
  (`json`, `argparse`, `pathlib`, `re`, `datetime`, `sys`) से लागू।
- **Safe & Resilient:** Windows PowerShell या command shells द्वारा उत्सर्जित
  UTF-8 with BOM (Byte Order Mark) स्वचालित रूप से संभालता है।
- **Traversal Protection:** सख्त regex और resolution checks से सभी फ़ाइल-नाम
  और डायरेक्टरी पाथ को traversal attacks से साफ़ करता है।
- **Second Brain Ready:** Obsidian, Logseq और Notion द्वारा समर्थित मानक YAML
  frontmatter बनाता है।
