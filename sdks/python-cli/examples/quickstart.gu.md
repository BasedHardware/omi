# omi-cli ગુજરાતી ક્વિકસ્ટાર્ટ માર્ગદર્શિકા (Gujarati Quickstart Guide)

> ટર્મિનલ પરથી Omi સાથે કામ કરવા માટેની વ્યવહારુ માર્ગદર્શિકા. ડેવલપર્સ અને AI એજન્ટ્સ બંને માટે ઉપયોગી.

`omi-cli` એ [Omi](https://omi.me) ડેવલપર API નો ઉપયોગ કરવા માટેનું સત્તાવાર કમાન્ડ-લાઈન ઈન્ટરફેસ (CLI) છે. Omi માં રહેલા ચાર મુખ્ય સંસાધનો (યાદો, વાતચીતો, કરવા યોગ્ય કાર્યો અને લક્ષ્યો) નું સંચાલન કરવા અને સ્ક્રિપ્ટો દ્વારા ઓટોમેશન કરવા માટે તે ખૂબ મદદરૂપ છે.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **સત્તાવાર દસ્તાવેજીકરણ:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **સોર્સ કોડ:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. ઇન્સ્ટોલેશન (Installation)

અન્ય પાયથોન પેકેજોથી અલગ અને સુરક્ષિત રાખવા માટે `pipx` દ્વારા ઇન્સ્ટોલ કરવું શ્રેષ્ઠ રીત છે:

```bash
# ભલામણ કરેલ રીત: pipx દ્વારા ઇન્સ્ટોલેશન
pipx install omi-cli

# અથવા pip નો ઉપયોગ કરીને
pip install omi-cli
```

> **મહત્વપૂર્ણ નોંધ: પેકેજ નામ અને કમાન્ડ નામ વચ્ચેનો તફાવત**
> * પાયથોન પેકેજનું નામ **`omi-cli`** છે (PyPI પર ઉપલબ્ધ `omi` એ અલગ પેકેજ છે, તેને ઇન્સ્ટોલ કરશો નહીં).
> * ઇન્સ્ટોલ કર્યા પછી ટર્મિનલમાં ચલાવવામાં આવતા કમાન્ડનું નામ **`omi`** છે.

ઇન્સ્ટોલેશન પૂર્ણ થયા પછી વર્ઝન અને મદદ ચકાસો:

```bash
omi --version
omi --help
```

---

## 2. પ્રમાણીકરણ (Authentication)

`omi-cli` બે પ્રકારની પ્રમાણીકરણ પદ્ધતિઓને સમર્થન આપે છે:

| પદ્ધતિ | મુખ્ય ઉપયોગ | નમૂના કમાન્ડ |
| :--- | :--- | :--- |
| **ડેવલપર API કી (`omi_dev_*`)** | CI/CD, ઓટોમેશન સ્ક્રિપ્ટો, AI એજન્ટ્સ | `omi auth login --api-key ...` અથવા એન્વાયર્નમેન્ટ વેરિયેબલ્સ |
| **બ્રાઉઝર OAuth (Google/Apple)** | ડેવલપરનું વ્યક્તિગત લેપટોપ / કમ્પ્યુટર | `omi auth login --browser` |

### ઇન્ટરેક્ટિવ લોગિન (Interactive Login)
કોઈપણ ફ્લેગ વગર કમાન્ડ ચલાવવાથી બ્રાઉઝર અથવા API કી પસંદ કરવાનો વિકલ્પ મળશે:

```bash
omi auth login
# 1) Browser — Google અથવા Apple ખાતા દ્વારા લૉગિન કરો (વ્યક્તિઓ માટે)
# 2) API key — app.omi.me પરથી મેળવેલ ડેવલપર કી દાખલ કરો (એજન્ટ્સ/CI માટે)
```

### સીધા બ્રાઉઝર દ્વારા લોગિન
```bash
omi auth login --browser
```

### API કી નો ઉપયોગ કરવો
[app.omi.me](https://app.omi.me) પર "Developer → API Keys" વિભાગમાંથી કી મેળવીને સેટ કરો:

```bash
# કમાન્ડ દ્વારા સેટ કરો
omi auth login --api-key omi_dev_...

# અથવા એન્વાયર્નમેન્ટ વેરિયેબલ દ્વારા સેટ કરો (CI/CD માટે શ્રેષ્ઠ)
export OMI_API_KEY=omi_dev_...
```

### પ્રમાણીકરણ સ્થિતિ ચકાસવી
* `omi auth status`: સ્થાનિક પ્રોફાઇલ, માસ્ક કરેલ ટોકન અને સમાપ્તિ સમય દર્શાવે છે (ઓફલાઇન કામ કરે છે).
* `omi auth whoami`: સર્વર પર રિક્વેસ્ટ મોકલીને કી માન્ય છે કે નહીં તે ચકાસે છે (ઇન્ટરનેટ જરૂરી છે).

```bash
omi auth status
omi auth whoami
```

ક્રેડેન્શિયલ્સ દૂર કરવા માટે લોગઆઉટ કરો:
```bash
omi auth logout
```

રૂપરેખાંકન ફાઇલ ડિફોલ્ટ રૂપે `~/.omi/config.toml` માં સુરક્ષિત રીતે સંગ્રહિત થાય છે. તેને કોઈની સાથે શેર કરશો નહીં.

---

## 3. મૂળભૂત વપરાશ (Basic Usage)

Omi ના ચાર મુખ્ય સંસાધનોનું સંચાલન:

### યાદો (Memories)
સિસ્ટમ દ્વારા શીખેલી હકીકતો અને માહિતીનું સંચાલન કરો:

```bash
# બધી યાદોની યાદી જુઓ
omi memory list

# નવી યાદ ઉમેરો
omi memory create "વપરાશકર્તા ડાર્ક મોડ પસંદ કરે છે" --category lifestyle

# ચોક્કસ યાદની વિગતો મેળવો
omi memory get <MEMORY_ID>
```

### વાતચીતો (Conversations)
પહેરી શકાય તેવા ઉપકરણ અથવા એપ્લિકેશન દ્વારા રેકોર્ડ કરાયેલ ઑડિયો અને ટ્રાન્સક્રિપ્ટો:

```bash
# તાજેતરની 5 વાતચીતો જુઓ
omi conversation list --limit 5

# વાતચીતની વિગતો અને સંપૂર્ણ ટ્રાન્સક્રિપ્ટ મેળવો
omi conversation get <CONVERSATION_ID> --include-transcript
```

### કરવા યોગ્ય કાર્યો (Action Items)
વાતચીતોમાંથી આપમેળે તારવેલા કાર્યો:

```bash
# માત્ર અધૂરા કાર્યોની યાદી જુઓ
omi action-item list --open

# કાર્ય પૂર્ણ થયું તરીકે ચિહ્નિત કરો
omi action-item complete <ACTION_ITEM_ID>
```

### લક્ષ્યો (Goals)
ટ્રેક કરવામાં આવતા લક્ષ્યો જુઓ:

```bash
# લક્ષ્યોની યાદી જુઓ
omi goal list
```

---

## 4. સ્ક્રિપ્ટીંગ અને JSON આઉટપુટ (`--json`)

`omi-cli` સીધા JSON આઉટપુટને સમર્થન આપે છે. `jq` અથવા અન્ય પ્રોગ્રામ્સ સાથે ઉપયોગ કરતી વખતે `--json` ગ્લોબલ વિકલ્પ હંમેશા **સબ-કમાન્ડની પહેલાં** મૂકવો આવશ્યક છે:

```bash
# યાદોને JSON માં મેળવીને ID અને સામગ્રી અલગ તારવો
omi --json memory list | jq '.[] | {id, content, category}'

# તાજેતરની વાતચીતોના શીર્ષકો જુઓ
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# બાકી રહેલા કાર્યો JSON માં જુઓ
omi --json action-item list --open | jq '.'
```

> **મહત્વપૂર્ણ નિયમ:** `--json` હંમેશા સબ-કમાન્ડની **પહેલાં** લખો:
> * સાચું: `omi --json memory list`
> * ખોટું: `omi memory list --json`

### ફાઇલમાં સાચવવું અને પૃષ્ઠીકરણ (Pagination)

```bash
# પ્રથમ 25 રેકોર્ડ ફાઇલમાં સાચવો
omi --json memory list --limit 25 --offset 0 > yaado-page-1.json

# પછીના 25 રેકોર્ડ મેળવો
omi --json memory list --limit 25 --offset 25 > yaado-page-2.json
```

---

## 5. એક્ઝિટ કોડ્સ (Exit Codes)

ઓટોમેશન સ્ક્રિપ્ટોમાં ભૂલો ઓળખવા માટે નીચે મુજબના એક્ઝિટ કોડ્સ ઉપલબ્ધ છે:

| કોડ | પ્રકાર | વર્ણન |
| :---: | :--- | :--- |
| `0` | Success | કમાન્ડ સફળતાપૂર્વક પૂર્ણ થયો |
| `1` | Usage Error | અમાન્ય ફ્લેગ્સ અથવા અપૂર્ણ પરિમાણો |
| `2` | Auth Error | લૉગિન કરેલ નથી, અમાન્ય કી અથવા ટોકનની મુદત સમાપ્ત |
| `3` | Server Error | સર્વર ભૂલ (5xx), નેટવર્ક સમસ્યા અથવા સમય સમાપ્તિ (Timeout) |
| `4` | Rate Limited | વિનંતી મર્યાદા વટાવી ગઈ (429 Too Many Requests) |
| `5` | Not Found | વિનંતી કરેલ સંસાધન મળ્યું નથી (404 Not Found) |

---

## 6. શેલ એન્વાયર્નમેન્ટ વેરિયેબલ્સ ઉદાહરણો

### Bash / Zsh (Linux / macOS)
```bash
# API કી સેટ કરો
export OMI_API_KEY="omi_dev_your_actual_key_here"

# કમાન્ડ ચલાવો
omi --json memory list --limit 10
```

### PowerShell (Windows)
```powershell
# API કી સેટ કરો
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# PowerShell માં JSON પાર્સિંગ
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

---

## 7. સ્થાનિક ડેસ્કટોપ API સાથે એકીકરણ (Local Desktop API)

Omi Desktop એપ ચાલુ હોય ત્યારે, ક્લાઉડની જરૂર વગર કમ્પ્યુટર પરનો ડેટા સીધો શોધી શકાય છે:

```bash
# સ્થાનિક API URL અને ટોકન રૂપરેખાંકિત કરો
omi local configure --url http://127.0.0.1:47778 --token YOUR_DESKTOP_TOKEN

# સ્થાનિક સ્થિતિ તપાસો
omi --json local status

# સ્ક્રીન ઇતિહાસમાં શોધો
omi --json local search-screen "પ્રોજેક્ટ પ્લાન" --days 7 --app Safari
```

---

## 8. પ્રોફાઇલ્સ સંચાલન (Profiles)

બહુવિધ એકાઉન્ટ્સ અથવા પરીક્ષણ વાતાવરણનું સંચાલન કરવા માટે `--profile` વિકલ્પનો ઉપયોગ કરો:

```bash
# વ્યક્તિગત પ્રોફાઇલ સાથે લૉગિન કરો
omi --profile personal auth login

# ઓફિસ પ્રોફાઇલ સાથે લૉગિન કરો
omi --profile work auth login

# ઇચ્છિત પ્રોફાઇલ હેઠળ કમાન્ડ ચલાવો
omi --profile work memory list
```
