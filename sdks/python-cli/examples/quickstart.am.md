# የ omi-cli ፈጣን መጀመሪያ መመሪያ (Amharic Quickstart)

> ከተርሚናል በቀጥታ ከ Omi ጋር ለመሥራት የሚያገለግል ተግባራዊ መመሪያ — ለገንቢዎችና ለራስ-ገዝ የ AI ወኪሎች።

`omi-cli` የ [Omi](https://omi.me) የገንቢ API ይፋዊ የትእዛዝ መስመር መገናኛ ነው። አራቱን ዋና ክፍሎች በተዋቀረና ራስ-ሰር ሊደረግ በሚችል መንገድ እንዲያስተዳድሩ ያስችልዎታል፦ ትውስታዎች (memories)፣ ውይይቶች (conversations)፣ የተግባር ነጥቦች (action items) እና ግቦች (goals)።

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **ይፋዊ ሰነድ:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **ምንጭ ኮድ:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

የትእዛዝ ስሞች፣ አማራጮች እና የፕሮግራሙ መልእክቶች በእንግሊዝኛ ይቀጥላሉ፤ የዚህ መመሪያ ማብራሪያ ብቻ ነው በአማርኛ የተጻፈው። ዋናው ምንጭ የእንግሊዝኛው README ነው።

---

## 1. መጫን

የጥገኝነት ግጭቶችን ለማስወገድና መሣሪያውን በተነጠለ አካባቢ ለማስኬድ `pipx` ይመከራል፦

```bash
# የሚመከር: በ pipx የተነጠለ መጫን
pipx install omi-cli

# አማራጭ: በነቃ የ Python ምናባዊ አካባቢ ውስጥ በ pip
pip install omi-cli
```

> **ማስታወሻ: የጥቅል ስም እና የትእዛዝ ስም**
> * በ PyPI ላይ ያለው የጥቅሉ ስም **`omi-cli`** ነው (`omi` የሚለው ስም የማይገናኝ ጥቅል ነው)።
> * በተርሚናል የሚያስኬዱት ትእዛዝ ግን **`omi`** ብቻ ነው።

መጫኑ መሥራቱን ያረጋግጡ፦

```bash
omi --version
omi --help
```

ተርሚናሉ `omi`ን ካላገኘ፣ ምናባዊ አካባቢው መንቃቱን ወይም `pipx` ተፈጻሚ ፋይሎችን የሚያስቀምጥበት ማውጫ በ `PATH` ውስጥ መኖሩን ያረጋግጡ።

---

## 2. ማንነት ማረጋገጥ (Authentication)

`omi-cli` ሁለት ዋና የማንነት ማረጋገጫ ዘዴዎችን ይደግፋል፦

| ዘዴ | አጠቃቀም | ምሳሌ |
| :--- | :--- | :--- |
| **የገንቢ API ቁልፍ (`omi_dev_*`)** | ስክሪፕቶች፣ CI/CD፣ ማሳያ የሌላቸው አገልጋዮች፣ የ AI ወኪሎች | `omi auth login --api-key ...` ወይም `OMI_API_KEY` |
| **የአሳሽ OAuth (Google/Apple)** | የአካባቢ የሥራ ጣቢያዎችና ገንቢዎች | `omi auth login --browser` (Google) / `--provider apple` |

### በይነተገናኝ መግባት
ዘዴውን በይነተገናኝ ለመምረጥ ያለ ምንም ባንዲራ ያስኪዱ፦

```bash
omi auth login
# 1) Browser — ለ Google መግቢያ አሳሹን ይከፍታል (ለ Apple `--provider apple` ይጠቀሙ)
# 2) API key — ከ app.omi.me የ API ቁልፍ ይለጥፉ (ግቤቱ ተደብቆ ይታያል)
```

### በአሳሽ በቀጥታ መግባት
```bash
# ነባሪ: የ Google መግቢያ
omi auth login --browser

# አማራጭ: የ Apple መግቢያ
omi auth login --browser --provider apple
```

### የገንቢ API ቁልፍ መጠቀም
ቁልፉን በ [app.omi.me](https://app.omi.me) ውስጥ **Developer → API Keys** ሥር ይፍጠሩ፦

```bash
# ወይም እንደ አካባቢ ተለዋዋጭ ይግለጹ (ለኮንቴይነሮችና ለ CI/CD የተሻለ)
export OMI_API_KEY="omi_dev_የእርስዎ_እውነተኛ_ቶከን"
```

> በጋራ አገልጋዮች ላይ ቁልፎችን እንደ ግልጽ የትእዛዝ መስመር ነጋሪ እሴት አያስተላልፉ፤ በይነተገናኝ መግቢያን ወይም `OMI_API_KEY`ን ይጠቀሙ።

```bash
# ቁልፉን በነቃው የአካባቢ መገለጫ ውስጥ ያስቀምጡ
omi auth login --api-key omi_dev_የእርስዎ_እውነተኛ_ቶከን
```

> `OMI_API_KEY` የሚሠራው የነቃው መገለጫ የተቀመጠ ቁልፍ ከሌለው ብቻ ነው። ቀደም ብለው በ `omi auth login` ገብተው ከሆነና የአካባቢ ተለዋዋጩ እንዲሠራ ከፈለጉ፣ መጀመሪያ `omi auth logout` ያስኪዱ።

### የማንነት ማረጋገጫ ሁኔታን መፈተሽ
* `omi auth status`፦ የነቃውን መገለጫና የተሸፈነ ማስረጃ ያሳያል (በአካባቢ/ከመስመር ውጭ ይሠራል፤ የማብቂያ ቀን ለ OAuth ቶከኖች ብቻ ነው የሚመለከተው)።
* `omi auth whoami`፦ ማስረጃው ትክክለኛ መሆኑን ለማረጋገጥ ወደ Omi አገልጋይ ጥያቄ ይልካል (አውታረ መረብ ይፈልጋል)።

```bash
omi auth status
omi auth whoami
```

የ OAuth ቶከንን እንደገና ሳይገቡ ማደስ፦

```bash
omi auth refresh
```

> `omi auth refresh` የሚሠራው በአሳሽ (OAuth) ለገቡ መገለጫዎች ብቻ ነው። በ API ቁልፍ ላይ ለተመሠረቱ መገለጫዎች የሚታደስ ነገር የለም፤ ትእዛዙ «Nothing to refresh» በሚል መልእክት እና በመውጫ ኮድ `1` ያበቃል።

መውጣት፦
```bash
omi auth logout
# OMI_API_KEY በአካባቢው ከተገለጸ እርሱንም ያስወግዱ (Bash/Zsh: `unset OMI_API_KEY`)።
```

---

## 3. ዋና ትእዛዞች

### ትውስታዎች (Memories)
Omi ያስቀመጣቸው የተዋቀሩ እውነታዎችና አውዳዊ ምልከታዎች፦

```bash
# ትውስታዎችን ዘርዝር
omi memory list

# አዲስ ትውስታ በምድብ ፍጠር
omi memory create "አጭር የቴክኒክ መልሶችን ከ Python ምሳሌዎች ጋር እመርጣለሁ" --category work

# የተወሰነ ትውስታ በመለያ አምጣ
omi memory get <MEMORY_ID>
```

### ውይይቶች (Conversations)
በ Omi መሣሪያዎች የተመዘገቡ የድምፅ ቅጂዎች፣ ግልባጮችና ንግግሮች፦

```bash
# የመጨረሻዎቹን 5 ውይይቶች ዘርዝር
omi conversation list --limit 5

# የአንድ ውይይት ዝርዝር ከሙሉ ግልባጭ ጋር
omi conversation get <CONVERSATION_ID> --include-transcript
```

### የተግባር ነጥቦች (Action Items)
ከውይይቶች በራስ-ሰር የተወሰዱ የሚሠሩ ሥራዎች፦

```bash
# ክፍት የተግባር ነጥቦችን ዘርዝር
omi action-item list --open

# አንድ የተግባር ነጥብ እንደተጠናቀቀ ምልክት አድርግ
omi action-item complete <ACTION_ITEM_ID>
```

### ግቦች (Goals)
የእድገት አመልካቾችና የረጅም ጊዜ ግቦች፦

```bash
# ንቁ ግቦችን ዘርዝር
omi goal list

# አዲስ የቁጥር ግብ ፍጠር
omi goal create "በቀን 2 ሊትር ውሃ መጠጣት" --type numeric --target 2 --unit liters

# የግብ የአሁኑን እሴት አዘምን (መለያ እና አዲስ እሴት)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. የተዋቀረ ራስ-ሰር አሠራር እና የ JSON ውጤት (`--json`)

`omi-cli` በቧንቧ መስመሮችና በመሣሪያ ሰንሰለቶች ውስጥ ራስ-ሰር ለማድረግ የተሠራ ነው። ዓለም-አቀፉ የ `--json` ባንዲራ ንጹሕና በማሽን የሚነበብ JSON ይመልሳል፦

```bash
# ትውስታዎችን እንደ JSON ዘርዝርና በ jq አጣራ
omi --json memory list | jq '.[] | {id, content, category}'

# የቅርብ ጊዜ ውይይቶች ርዕሶች
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# ሁሉንም ክፍት የተግባር ነጥቦች እንደ ጥሬ JSON
omi --json action-item list --open | jq '.'
```

> **አስፈላጊ የአገባብ ሕግ፦**
> `--json` **ዓለም-አቀፍ አማራጭ** ነው እና ከንዑስ ትእዛዙ **በፊት** መቀመጥ አለበት፦
> * ትክክል፦ `omi --json memory list`
> * ስህተት፦ `omi memory list --json`

### ገጽ መከፋፈል
የ `list` ትእዛዞች `--limit` እና `--offset` ይደግፋሉ፦

```bash
omi --json memory list --limit 50 --offset 50
```

### ወደ ፋይል መላክ
የ ANSI ቀለሞች ወይም የቁጥጥር ቁምፊዎች ፋይሉን እንዳይበክሉ፣ stdoutን በቀጥታ በሼሉ ውስጥ ያዙሩት፦

```bash
# ትውስታዎችን በቀጥታ ወደ ንጹሕ የ JSON ፋይል ላክ
omi --json memory list > memories.json
```

---

## 5. የመውጫ ኮዶች (Exit Codes Contract)

በ CI/CD እና በስክሪፕቶች ውስጥ አስተማማኝ የስህተት አያያዝ እንዲኖር፣ `omi-cli` ጥብቅ የመውጫ ኮድ ውል ይከተላል (`omi_cli/errors.py` ይመልከቱ)፦

| ኮድ | ስም | መግለጫ እና ምሳሌ |
| :---: | :--- | :--- |
| `0` | **ስኬት (`EXIT_OK`)** | ተግባሩ ያለ ስህተት ተጠናቋል። |
| `1` | **የአጠቃቀም ስህተት (`EXIT_USAGE`)** | የ omi-cli የራሱ የማረጋገጫ ስህተቶች፦ አብረው የማይሄዱ `--browser` እና `--api-key`፣ በበይነተገናኝ መግቢያ ውስጥ ልክ ያልሆነ ምርጫ፣ ባዶ የ stdin ግቤት፣ ወይም በ API ቁልፍ መገለጫ ላይ `omi auth refresh`። |
| `2` | **የማንነት ማረጋገጫ ስህተት (`EXIT_AUTH`)** | የጠፋ ወይም ልክ ያልሆነ ማስረጃ፣ ወይም ጊዜው ያለፈ ክፍለ ጊዜ። ማስታወሻ፦ ያልታወቀ ባንዲራ ወይም የጎደለ ነጋሪ እሴት በ Click ራሱ ተቀባይነት ስለማያገኝ እንዲሁ በኮድ `2` ይወጣል። |
| `3` | **የአገልጋይ ስህተት (`EXIT_SERVER`)** | ከ Omi አገልጋይ HTTP 5xx ወይም የአውታረ መረብ መቋረጥ። |
| `4` | **የፍጥነት ገደብ (`EXIT_RATE_LIMITED`)** | HTTP 429 — በአጭር ጊዜ ውስጥ በጣም ብዙ ጥያቄዎች። |
| `5` | **አልተገኘም (`EXIT_NOT_FOUND`)** | HTTP 404 — የተጠየቀው ሀብት (ትውስታ፣ ውይይት፣ የተግባር ነጥብ) የለም። |

---

## 6. ለተለያዩ ሼሎች ምሳሌዎች

### Bash / Zsh (Linux / macOS)
```bash
# ለዚህ ክፍለ ጊዜ የ API ቁልፍ አዘጋጅ
export OMI_API_KEY="omi_dev_የእርስዎ_እውነተኛ_ቶከን"

# ትእዛዝ አስኪድና የመውጫ ኮዱን ፈትሽ
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "ትውስታዎችን ከ Omi ማምጣት አልተሳካም።" >&2
fi
```

### PowerShell (Windows)
```powershell
# በ PowerShell ውስጥ የአካባቢ ተለዋዋጭ ግለጽ
$env:OMI_API_KEY = "omi_dev_የእርስዎ_እውነተኛ_ቶከን"

# የ JSON ውጤትን በቀጥታ ወደ PowerShell ነገር ቀይር
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# በ $LASTEXITCODE ስህተት ፈትሽ
if ($LASTEXITCODE -ne 0) {
    Write-Error "የ Omi ትእዛዝ በመውጫ ኮድ $LASTEXITCODE አልተሳካም።"
}
```

---

## 7. የአካባቢ ዴስክቶፕ API ውህደት (Omi Desktop)

Omi Desktop በማሽንዎ ላይ ሲሠራ (ነባሪ ወደብ 47778)፣ በደመናው ሳያልፉ ከአካባቢው አውድ ጋር በቀጥታ መሥራት ይችላሉ፦

```bash
# የአካባቢ API ግንኙነትን አዋቅር (ቶከኑን ለመጠበቅ የአካባቢ ተለዋዋጮችን ይጠቀሙ)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "የ Desktop ቶከን ያስገቡ: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# የአካባቢ ግንኙነት ሁኔታን አረጋግጥ
omi --json local status

# በአካባቢ የማያ ገጽ ታሪክ ውስጥ ፈልግ
omi --json local search-screen "የሩብ ዓመት ሪፖርት" --days 7 --app Safari
```

ከአካባቢ ተለዋዋጮች ይልቅ ቅንብሮቹን በመገለጫው ላይ ማስቀመጥም ይችላሉ፦ `omi local configure --url http://127.0.0.1:47778 --token ...`።

---

## 8. የበርካታ መገለጫዎች አስተዳደር (Profiles)

በግል መለያ፣ በሥራ መገለጫ ወይም በሙከራ አካባቢ መካከል ያለችግር ለመቀያየር `--profile`ን ይጠቀሙ። ቅንብሮቹ በ `~/.omi/config.toml` ውስጥ ይቀመጣሉ። የቅድሚያ ቅደም ተከተል፦ የ `--profile` ባንዲራ፣ ከዚያ የ `OMI_PROFILE` አካባቢ ተለዋዋጭ፣ በመጨረሻም `default` መገለጫ።

```bash
# የግል መገለጫ ፍጠርና ግባ
omi --profile personal auth login

# የሥራ መገለጫ ፍጠርና ግባ
omi --profile work auth login

# በተወሰነ መገለጫ ትእዛዝ አስኪድ
omi --profile work memory list

# መገለጫውን በአካባቢ ተለዋዋጭ ምረጥ
export OMI_PROFILE=work
omi memory list

# ለሙከራ ብጁ የመጨረሻ ነጥብ ተጠቀም
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. የደኅንነት መመሪያዎችና ምርጥ ልምዶች

* **ቁልፎችን በኮድ ውስጥ አያስቀምጡ፦** የ API ቁልፎችን (`omi_dev_*`) በጭራሽ ወደ Git ማከማቻ አያስገቡ። በ `.gitignore` ውስጥ የተካተቱ `.env` ፋይሎችን ወይም አስተማማኝ የምስጢር አስተዳዳሪዎችን ይጠቀሙ።
* **የሼል ታሪክን ይጠብቁ፦** በጋራ አገልጋዮች ላይ ቁልፎችን እንደ ግልጽ የትእዛዝ መስመር ነጋሪ እሴት አያስተላልፉ፤ በይነተገናኝ መግቢያን ወይም `OMI_API_KEY`ን ይጠቀሙ።
* **የማውጫ ፈቃዶችን ያጥብቁ፦** በ Unix/macOS ላይ የውቅር ማውጫው የተገደበ ፈቃድ እንዳለው ያረጋግጡ፦
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **የክፍለ ጊዜ ጽዳት፦** ጊዜያዊ አካባቢዎችን ሲያፈርሱ የአካባቢ ተለዋዋጩን ማስወገድ አይርሱ፦
  ```bash
  unset OMI_API_KEY
  ```
