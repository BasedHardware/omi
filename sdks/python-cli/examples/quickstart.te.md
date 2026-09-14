# omi-cli తెలుగు క్విక్‌స్టార్ట్ గైడ్ (Telugu Quickstart Guide)

> టెర్మినల్ నుండి Omi తో సంభాషించడానికి ప్రాక్టికల్ గైడ్. వ్యక్తులు మరియు AI ఏజెంట్లు ఇద్దరికీ ఉపయోగకరంగా ఉంటుంది.

`omi-cli` అనేది [Omi](https://omi.me) డెవలపర్ API ని ఉపయోగించడానికి అధికారిక కమాండ్-లైన్ ఇంటర్‌ఫేస్. Omi లోని నాలుగు ముఖ్యమైన వనరులను (జ్ఞాపకాలు, సంభాషణలు, కార్యాచరణ అంశాలు మరియు లక్ష్యాలు) సమర్థవంతంగా నిర్వహించడానికి మరియు స్క్రిప్ట్‌ల ద్వారా ఆటోమేట్ చేయడానికి ఇది ఉపయోగపడుతుంది.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **అధికారిక డాక్యుమెంటేషన్:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **సోర్స్ కోడ్:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. ఇన్‌స్టాలేషన్ (Installation)

డిపెండెన్సీలను వేరుగా ఉంచడానికి `pipx` ఉపయోగించి ఇన్‌స్టాల్ చేయడం ఉత్తమమైన పద్ధతి:

```bash
# సిఫార్సు చేయబడిన పద్ధతి: pipx ఉపయోగించి ఇన్‌స్టాలేషన్
pipx install omi-cli

# లేదా pip ఉపయోగించి
pip install omi-cli
```

> **ముఖ్యమైన గమనిక: ప్యాకేజీ పేరు మరియు కమాండ్ పేరు మధ్య వ్యత్యాసం**
> * పైథాన్ ప్యాకేజీ పేరు **`omi-cli`** (PyPI లోని `omi` అనేది సంబంధం లేని వేరే ప్యాకేజీ, దానిని ఇన్‌స్టాల్ చేయవద్దు).
> * ఇన్‌స్టాలేషన్ తర్వాత టెర్మినల్‌లో రన్ చేసే కమాండ్ పేరు **`omi`**.

ఇన్‌స్టాలేషన్ పూర్తయిన తర్వాత వెర్షన్ మరియు సహాయాన్ని తనిఖీ చేయండి:

```bash
omi --version
omi --help
```

---

## 2. ప్రామాణీకరణ (Authentication)

`omi-cli` రెండు రకాల ప్రామాణీకరణ పద్ధతులకు మద్దతు ఇస్తుంది:

| పద్ధతి | ప్రధాన ఉపయోగం | ఉదాహరణ కమాండ్ |
| :--- | :--- | :--- |
| **డెవలపర్ API కీ (`omi_dev_*`)** | CI/CD, ఆటోమేషన్ స్క్రిప్ట్‌లు, AI ఏజెంట్లు | `omi auth login --api-key ...` లేదా ఎన్విరాన్‌మెంట్ వేరియబుల్స్ |
| **బ్రౌజర్ OAuth (Google/Apple)** | డెవలపర్ పర్సనల్ ల్యాప్‌టాప్ / కంప్యూటర్ | `omi auth login --browser` |

### ఇంటరాక్టివ్ లాగిన్ (Interactive Login)
ఎటువంటి ఫ్లాగ్‌లు లేకుండా కమాండ్ రన్ చేస్తే బ్రౌజర్ లేదా API కీ ఎంచుకునే ఆప్షన్ వస్తుంది:

```bash
omi auth login
# 1) Browser — Google లేదా Apple ఖాతా ద్వారా లాగిన్ అవ్వండి (వ్యక్తుల కోసం)
# 2) API key — app.omi.me నుండి డెవలపర్ కీని పేస్ట్ చేయండి (ఏజెంట్లు/CI కోసం)
```

### నేరుగా బ్రౌజర్ ద్వారా లాగిన్
```bash
omi auth login --browser
```

### API కీని ఉపయోగించడం
[app.omi.me](https://app.omi.me) లోని "Developer → API Keys" నుండి డెవలపర్ కీని పొంది సెట్ చేయండి:

```bash
# కమాండ్ ద్వారా సెట్ చేయండి
omi auth login --api-key omi_dev_...

# లేదా ఎన్విరాన్‌మెంట్ వేరియబుల్ ద్వారా సెట్ చేయండి (CI/CD కి ఉత్తమం)
export OMI_API_KEY=omi_dev_...
```

### ప్రామాణీకరణ స్థితిని తనిఖీ చేయడం
* `omi auth status`: స్థానిక ప్రొఫైల్, మాస్క్ చేయబడిన టోకెన్ మరియు గడువు వివరాలను చూపిస్తుంది (ఆఫ్‌లైన్‌లో పనిచేస్తుంది).
* `omi auth whoami`: సర్వర్‌కు నేరుగా రిక్వెస్ట్ పంపి కీ పనిచేస్తుందో లేదో ధృవీకరిస్తుంది (ఇంటర్నెట్ అవసరం).

```bash
omi auth status
omi auth whoami
```

క్రెడెన్షియల్స్ తొలగించడానికి లాగౌట్ చేయండి:
```bash
omi auth logout
```

కాన్ఫిగరేషన్ ఫైల్ డిఫాల్ట్‌గా `~/.omi/config.toml` లో భద్రపరచబడుతుంది. దీనిని ఎవరితోనూ పంచుకోవద్దు.

---

## 3. ప్రాథమిక ఆదేశాలు (Basic Usage)

Omi లోని నాలుగు ప్రధాన వనరులను నిర్వహించడం:

### జ్ఞాపకాలు (Memories)
వ్యవస్థ నేర్చుకున్న వాస్తవాలు మరియు సమాచారాన్ని నిర్వహించండి:

```bash
# జ్ఞాపకాల జాబితాను చూడండి
omi memory list

# కొత్త జ్ఞాపకాన్ని సృష్టించండి
omi memory create "వినియోగదారుడు డార్క్ మోడ్‌ను ఇష్టపడతారు" --category lifestyle

# నిర్దిష్ట జ్ఞాపకం వివరాలను చూడండి
omi memory get <MEMORY_ID>
```

### సంభాషణలు (Conversations)
వేరబుల్ పరికరం లేదా యాప్ నుండి రికార్డ్ చేయబడిన ఆడియో మరియు ట్రాన్స్‌క్రిప్ట్‌లు:

```bash
# ఇటీవల జరిగిన 5 సంభాషణలను చూడండి
omi conversation list --limit 5

# సంభాషణ వివరాలు మరియు పూర్తి ట్రాన్స్‌క్రిప్ట్‌ను చూడండి
omi conversation get <CONVERSATION_ID> --include-transcript
```

### కార్యాచరణ అంశాలు (Action Items)
సంభాషణల నుండి ఆటోమేటిక్‌గా సంగ్రహించబడిన పనులు:

```bash
# ఇంకా పూర్తికాని పనుల జాబితా మాత్రమే చూడండి
omi action-item list --open

# ఒక పని పూర్తయినట్లు మార్క్ చేయండి
omi action-item complete <ACTION_ITEM_ID>
```

### లక్ష్యాలు (Goals)
ట్రాక్ చేయబడుతున్న లక్ష్యాలను చూడండి:

```bash
# లక్ష్యాల జాబితాను చూడండి
omi goal list
```

---

## 4. స్క్రిప్టింగ్ మరియు JSON అవుట్‌పుట్ (`--json`)

`omi-cli` స్థానిక JSON అవుట్‌పుట్‌కు మద్దతు ఇస్తుంది. `jq` లేదా ఇతర ప్రోగ్రామ్‌లతో ఉపయోగించేటప్పుడు `--json` గ్లోబల్ ఆప్షన్‌ను **సబ్-కమాండ్‌కు ముందే** ఇవ్వాలి:

```bash
# జ్ఞాపకాలను JSON లో పొంది ID మరియు కంటెంట్‌ను సంగ్రహించండి
omi --json memory list | jq '.[] | {id, content, category}'

# ఇటీవలి సంభాషణల శీర్షికలను చూడండి
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# పెండింగ్‌లో ఉన్న పనులను JSON లో చూడండి
omi --json action-item list --open | jq '.'
```

> **ముఖ్యమైన నియమం:** `--json` ఎల్లప్పుడూ సబ్-కమాండ్‌కు **ముందే** ఉంచండి:
> * సరైనది: `omi --json memory list`
> * తప్పు: `omi memory list --json`

### ఫైల్‌లోకి సేవ్ చేయడం మరియు పేజీల విభజన (Pagination)

```bash
# మొదటి 25 రికార్డులను ఫైల్‌లో సేవ్ చేయండి
omi --json memory list --limit 25 --offset 0 > gnapakaalu-page-1.json

# తదుపరి 25 రికార్డులను పొందండి
omi --json memory list --limit 25 --offset 25 > gnapakaalu-page-2.json
```

---

## 5. ఎగ్జిట్ కోడ్‌లు (Exit Codes)

ఆటోమేషన్ స్క్రిప్ట్‌లలో ఎర్రర్‌లను గుర్తించడానికి ఎగ్జిట్ కోడ్‌లు క్రింది విధంగా ఉంటాయి:

| కోడ్ | రకం | వివరణ |
| :---: | :--- | :--- |
| `0` | Success | కమాండ్ విజయవంతంగా పూర్తయింది |
| `1` | Usage Error | తప్పుడు ఫ్లాగ్‌లు లేదా అసంపూర్ణ పారామితులు |
| `2` | Auth Error | లాగిన్ చేయలేదు, చెల్లని API కీ లేదా టోకెన్ గడువు ముగిసింది |
| `3` | Server Error | సర్వర్ ఎర్రర్ (5xx), నెట్‌వర్క్ సమస్య లేదా టైమ్‌అవుట్ |
| `4` | Rate Limited | రిక్వెస్ట్ పరిమితి మించిపోయింది (429 Too Many Requests) |
| `5` | Not Found | అభ్యర్థించిన వనరు కనుగొనబడలేదు (404 Not Found) |

---

## 6. షెల్ ఎన్విరాన్‌మెంట్ వేరియబుల్స్ ఉదాహరణలు

### Bash / Zsh (Linux / macOS)
```bash
# API కీని సెట్ చేయండి
export OMI_API_KEY="omi_dev_your_actual_key_here"

# కమాండ్ రన్ చేయండి
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API కీని సెట్ చేయండి
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# PowerShell లో JSON పార్సింగ్
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. లోకల్ డెస్క్‌టాప్ API తో అనుసంధానం (Local Desktop API)

Omi Desktop యాప్ నడుస్తున్నప్పుడు, క్లౌడ్ అవసరం లేకుండా కంప్యూటర్‌లోని డేటాను నేరుగా శోధించవచ్చు:

```bash
# లోకల్ API URL మరియు టోకెన్ కాన్ఫిగర్ చేయండి
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# లోకల్ స్థితిని తనిఖీ చేయండి
omi --json local status

# స్క్రీన్ చరిత్రను శోధించండి
omi --json local search-screen "ప్రాజెక్ట్ ప్రణాళిక" --days 7 --app Safari
```

---

## 8. ప్రొఫైల్స్ నిర్వహణ (Profiles)

బహుళ ఖాతాలు లేదా టెస్టింగ్ పరిసరాలను నిర్వహించడానికి `--profile` ఆప్షన్ ఉపయోగించండి:

```bash
# వ్యక్తిగత ప్రొఫైల్‌తో లాగిన్ అవ్వండి
omi --profile personal auth login

# ఆఫీస్ ప్రొఫైల్‌తో లాగిన్ అవ్వండి
omi --profile work auth login

# కావలసిన ప్రొఫైల్ ద్వారా కమాండ్స్ రన్ చేయండి
omi --profile work memory list
```
