# omi-cli தமிழ் விரைவு தொடக்க வழிகாட்டி (Tamil Quickstart Guide)

> முனையத்திலிருந்து (Terminal) Omi உடன் தொடர்புகொள்வதற்கான நடைமுறை வழிகாட்டி. மனித டெவலப்பர்கள் மற்றும் AI முகவர்கள் (Agents) இருவருக்கும் பயனுள்ளதாக இருக்கும்.

`omi-cli` என்பது [Omi](https://omi.me) டெவலப்பர் API-ஐப் பயன்படுத்துவதற்கான அதிகாரப்பூர்வ கட்டளை வரி இடைமுகம் (CLI) ஆகும். Omi-இல் உள்ள நான்கு முக்கிய ஆதாரங்களை (நினைவுகள், உரையாடல்கள், செய்ய வேண்டிய பணிகள் மற்றும் இலக்குகள்) திறம்பட நிர்வகிக்கவும் ஸ்கிரிப்டுகள் மூலம் தானியக்கமாக்கவும் இது உதவுகிறது.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **அதிகாரப்பூர்வ ஆவணங்கள்:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **மூலக் குறியீடு:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. நிறுவுதல் (Installation)

பிற பைதான் தொகுப்புகளிலிருந்து தனிமைப்படுத்த `pipx` மூலம் நிறுவுவது சிறந்த வழி:

```bash
# பரிந்துரைக்கப்படும் முறை: pipx மூலம் நிறுவுதல்
pipx install omi-cli

# அல்லது pip மூலம் நிறுவுதல்
pip install omi-cli
```

> **முக்கிய குறிப்பு: தொகுப்புப் பெயர் மற்றும் கட்டளைப் பெயர் இடையே உள்ள வேறுபாடு**
> * பைதான் தொகுப்புப் பெயர் **`omi-cli`** (PyPI-இல் உள்ள `omi` என்பது வேறுபட்ட தொடர்பற்ற தொகுப்பு, அதை நிறுவ வேண்டாம்).
> * நிறுவிய பின் முனையத்தில் இயக்கும் கட்டளையின் பெயர் **`omi`**.

நிறுவல் முடிந்ததும் பதிப்பு மற்றும் உதவித் தகவலைச் சரிபார்க்கவும்:

```bash
omi --version
omi --help
```

---

## 2. அங்கீகரிப்பு (Authentication)

`omi-cli` இரண்டு முறைகளில் அங்கீகரிப்பை ஆதரிக்கிறது:

| முறை | முக்கிய பயன்பாடு | மாதிரி கட்டளை |
| :--- | :--- | :--- |
| **டெவலப்பர் API சாவி (`omi_dev_*`)** | CI/CD, தானியக்க ஸ்கிரிப்டுகள், AI முகவர்கள் | `omi auth login --api-key ...` அல்லது சுற்றுச்சூழல் மாறிகள் |
| **உலாவி OAuth (Google/Apple)** | டெவலப்பரின் தனிப்பட்ட மடிக்கணினி / கணினி | `omi auth login --browser` |

### ஊடாடும் உள்நுழைவு (Interactive Login)
எந்தக் கொடியும் இல்லாமல் இயக்கினால் உலாவி அல்லது API சாவியைத் தேர்ந்தெடுக்கும் விருப்பம் தோன்றும்:

```bash
omi auth login
# 1) Browser — Google அல்லது Apple கணக்கு மூலம் உள்நுழைக (மனிதர்களுக்கு)
# 2) API key — app.omi.me தளத்திலிருந்து டெவலப்பர் சாவியை ஒட்டவும் (முகவர்கள்/CI-க்கு)
```

### நேரடியாக உலாவி மூலம் உள்நுழைவு
```bash
omi auth login --browser
```

### API சாவியைப் பயன்படுத்துதல்
[app.omi.me](https://app.omi.me) தளத்தில் "Developer → API Keys" பகுதிக்குச் சென்று சாவியைப் பெற்று அமைக்கவும்:

```bash
# கட்டளை மூலம் அமைத்தல்
omi auth login --api-key omi_dev_...

# அல்லது சுற்றுச்சூழல் மாறி மூலம் அமைத்தல் (CI/CD-க்கு சிறந்தது)
export OMI_API_KEY=omi_dev_...
```

### அங்கீகார நிலையைச் சரிபார்த்தல்
* `omi auth status`: உள்ளூர் சுயவிவரம், மறைக்கப்பட்ட டோக்கன் மற்றும் காலாவதி விவரங்களைக் காட்டும் (ஆஃப்லைனில் செயல்படும்).
* `omi auth whoami`: சேவையகத்திற்கு கோரிக்கையை அனுப்பி சாவி செயல்படுகிறதா என உறுதிப்படுத்தும் (இணைய இணைப்பு தேவை).

```bash
omi auth status
omi auth whoami
```

சான்றுகளை நீக்க வெளியேறவும் (Logout):
```bash
omi auth logout
```

அமைப்புகள் கோப்பு இயல்புநிலையாக `~/.omi/config.toml` இல் பாதுகாப்பாக சேமிக்கப்படும். இதனை யாரிடமும் பகிர வேண்டாம்.

---

## 3. அடிப்படைப் பயன்பாடு (Basic Usage)

Omi-இன் நான்கு முக்கிய வளங்களை நிர்வகிப்பது:

### நினைவுகள் (Memories)
அமைப்பு கற்றுக்கொண்ட தகவல்கள் மற்றும் உண்மைகளை நிர்வகிக்கவும்:

```bash
# நினைவுகளின் பட்டியலைக் காண
omi memory list

# புதிய நினைவை உருவாக்க
omi memory create "பயனர் டார்க் மோடை (Dark Mode) விரும்புகிறார்" --category lifestyle

# குறிப்பிட்ட நினைவின் விவரங்களைப் பெற
omi memory get <MEMORY_ID>
```

### உரையாடல்கள் (Conversations)
அணியக்கூடிய சாதனம் அல்லது செயலியிலிருந்து பதிவுசெய்யப்பட்ட ஆடியோ மற்றும் உரைத் தொகுப்புகள்:

```bash
# சமீபத்திய 5 உரையாடல்களைக் காண
omi conversation list --limit 5

# உரையாடல் விவரங்கள் மற்றும் முழு உரைவடிவத்தைப் பெற
omi conversation get <CONVERSATION_ID> --include-transcript
```

### செய்ய வேண்டிய பணிகள் (Action Items)
உரையாடல்களிலிருந்து தானாகப் பிரித்தெடுக்கப்பட்ட பணிகள்:

```bash
# முடிவடையாத பணிகளின் பட்டியலை மட்டும் காண
omi action-item list --open

# ஒரு பணியை முடித்ததாகக் குறிக்க
omi action-item complete <ACTION_ITEM_ID>
```

### இலக்குகள் (Goals)
கண்காணிக்கப்படும் இலக்குகளைக் காண:

```bash
# இலக்குகளின் பட்டியலைக் காண
omi goal list
```

---

## 4. ஸ்கிரிப்டிங் மற்றும் JSON வெளியீடு (`--json`)

`omi-cli` நேரடி JSON வெளியீட்டை ஆதரிக்கிறது. `jq` அல்லது பிற நிரல்களுடன் பயன்படுத்தும்போது `--json` உலகளாவிய விருப்பத்தை **துணைக்கட்டளைக்கு முன்பே** இட வேண்டும்:

```bash
# நினைவுகளை JSON வடிவத்தில் பெற்று ID மற்றும் உள்ளடக்கத்தைப் பிரித்தெடுக்க
omi --json memory list | jq '.[] | {id, content, category}'

# சமீபத்திய உரையாடல்களின் தலைப்புகளைக் காண
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# நிலுவையில் உள்ள பணிகளை JSON வடிவில் காண
omi --json action-item list --open | jq '.'
```

> **முக்கிய விதி:** `--json` கொடியை எப்போதும் துணைக்கட்டளைக்கு **முன்பு** வைக்கவும்:
> * சரியானது: `omi --json memory list`
> * தவறானது: `omi memory list --json`

### கோப்பில் சேமித்தல் மற்றும் பக்கமாக்கல் (Pagination)

```bash
# முதல் 25 பதிவுகளைக் கோப்பில் சேமிக்க
omi --json memory list --limit 25 --offset 0 > ninaivukal-page-1.json

# அடுத்த 25 பதிவுகளைப் பெற
omi --json memory list --limit 25 --offset 25 > ninaivukal-page-2.json
```

---

## 5. வெளியேற்றுக் குறியீடுகள் (Exit Codes)

தானியக்க ஸ்கிரிப்டுகளில் பிழைகளைக் கண்டறிய பின்வரும் வெளியேற்றுக் குறியீடுகள் உதவுகின்றன:

| குறியீடு | வகை | விளக்கம் |
| :---: | :--- | :--- |
| `0` | Success | கட்டளை வெற்றிகரமாக முடிந்தது |
| `1` | Usage Error | தவறான கொடிகள் அல்லது முழுமையற்ற அளவுருக்கள் |
| `2` | Auth Error | உள்நுழையவில்லை, தவறான API சாவி அல்லது காலாவதியான டோக்கன் |
| `3` | Server Error | சேவையகப் பிழை (5xx), நெட்வொர்க் சிக்கல் அல்லது காலமுடிவு (Timeout) |
| `4` | Rate Limited | கோரிக்கை வரம்பு மீறப்பட்டது (429 Too Many Requests) |
| `5` | Not Found | கோரப்பட்ட ஆதாரம் கிடைக்கவில்லை (404 Not Found) |

---

## 6. ஷெல் சுற்றுச்சூழல் மாறிகள் மாதிரி

### Bash / Zsh (Linux / macOS)
```bash
# API சாவியை அமைக்க
export OMI_API_KEY="omi_dev_your_actual_key_here"

# கட்டளையை இயக்க
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API சாவியை அமைக்க
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# PowerShell-இல் JSON பகுப்பாய்வு
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. உள்ளூர் டெஸ்க்டாப் API உடன் ஒருங்கிணைப்பு (Local Desktop API)

Omi Desktop செயலி இயங்கும்போது, கிளவுட் தேவையின்றி கணினியில் உள்ள தரவை நேரடியாகத் தேடலாம்:

```bash
# உள்ளூர் API முகவரி மற்றும் டோக்கனை உள்ளமைக்க
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# உள்ளூர் நிலையைச் சரிபார்க்க
omi --json local status

# திரை வரலாற்றைத் தேட
omi --json local search-screen "திட்ட வரைவு" --days 7 --app Safari
```

---

## 8. சுயவிவரங்கள் மேலாண்மை (Profiles)

பல கணக்குகள் அல்லது சோதனைச் சூழல்களை நிர்வகிக்க `--profile` விருப்பத்தைப் பயன்படுத்தவும்:

```bash
# தனிப்பட்ட சுயவிவரத்தில் உள்நுழைய
omi --profile personal auth login

# அலுவலக சுயவிவரத்தில் உள்நுழைய
omi --profile work auth login

# விரும்பிய சுயவிவரத்தின் கீழ் கட்டளைகளை இயக்க
omi --profile work memory list
```
