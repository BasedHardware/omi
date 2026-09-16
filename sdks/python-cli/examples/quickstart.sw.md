# omi-cli Mwongozo wa Kuanza Haraka (Swahili Quickstart)

> Mwongozo wa vitendo wa kutumia Omi moja kwa moja kutoka kwenye kituo cha amri (terminal), ulioundwa kwa ajili ya watengenezaji programu na mifumo ya kiotomatiki ya AI.

`omi-cli` ni kiolesura rasmi cha mstari wa amri (CLI) kwa ajili ya API ya watengenezaji wa [Omi](https://omi.me). Inatoa ufikiaji uliopangwa kwa rasilimali 4 kuu za Omi: kumbukumbu (memories), mazungumzo (conversations), majukumu ya kutenda (action items), na malengo (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Nyaraka Rasmi:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Msimbo Chanzo:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Usakinishaji

Ili kuepuka migongano ya vifurushi na kuhakikisha mazingira safi yaliyojitenga, inashauriwa sana kutumia `pipx`:

```bash
# Njia inayopendekezwa: usakinishaji uliotengwa kupitia pipx
pipx install omi-cli

# Njia mbadala: usakinishaji wa kawaida kupitia pip (kwa mfano kwenye virtualenv)
pip install omi-cli
```

> **Ufafanuzi Muhimu: Jina la Kifurushi dhidi ya Jina la Amri**
> * Jina rasmi la usambazaji katika PyPI ni **`omi-cli`** (kifurushi cha `omi` pekee ni mradi tofauti usiohusiana).
> * Amri inayotekelezwa kwenye kituo cha amri ni moja kwa moja: **`omi`**.

Thibitisha kuwa usakinishaji umefaulu kwa kuangalia toleo na menyu ya msaada:

```bash
omi --version
omi --help
```

---

## 2. Uthibitishaji (Authentication)

`omi-cli` inasaidia njia kuu mbili za uthibitishaji:

| Njia | Matumizi Yanayokusudiwa | Mfano wa Amri |
| :--- | :--- | :--- |
| **Ufunguo wa API wa Mtengenezaji (`omi_dev_*`)** | Mifumo ya kiotomatiki, seva za CI/CD, mawakala wa AI | `omi auth login --api-key ...` au `OMI_API_KEY` |
| **Kuingia kwa Kivinjari kupitia OAuth (Google/Apple)** | Utengenezaji wa kawaida kwenye kompyuta binafsi | `omi auth login --browser` (Google) / `--provider apple` |

### Kuingia kwa Maingiliano
Kutekeleza amri bila vigezo vya ziada kunafungua menyu ya maingiliano:

```bash
omi auth login
# 1) Browser: Ingia kupitia kivinjari na Google (kwa Apple tumia bendera `--provider apple`)
# 2) API key: Weka ufunguo wa API uliotolewa kutoka app.omi.me
```

### Kuingia Moja kwa Moja kupitia Kivinjari
```bash
# Kuingia kwa kawaida kwa akaunti ya Google
omi auth login --browser

# Kuingia kwa kutumia kitambulisho cha Apple
omi auth login --browser --provider apple
```

### Kuingia kwa Ufunguo wa API
Tengeneza ufunguo wa API kwenye dashibodi ya [app.omi.me](https://app.omi.me) chini ya sehemu ya **Developer -> API Keys**:

```bash
# Hifadhi ufunguo kwenye wasifu wa sasa wa ndani
omi auth login --api-key omi_dev_...

# Au weka kama kigezo cha mazingira (inapendekezwa kwa vyombo vya Docker na CI/CD):
# Kumbuka: Ikiwa wasifu wako tayari una ufunguo uliohifadhiwa, kwanza tekeleza `omi auth logout`.
export OMI_API_KEY="omi_dev_ufunguo_wako_hapa"
```

### Kuangalia Hali ya Uthibitishaji
* `omi auth status`: Inaonyesha wasifu unaotumika na kitambulisho kilichofichwa bila kufanya ombi la mtandao (inafanya kazi nje ya mtandao).
* `omi auth whoami`: Inatuma ombi la kuthibitisha kwa seva ya Omi ili kuhakikisha kipindi bado ni halali (inahitaji mtandao).

```bash
omi auth status
omi auth whoami
```

### Kuondoka (Logout)
```bash
omi auth logout
# Ikiwa ulitumia kigezo cha mazingira cha OMI_API_KEY, kiondoe kwenye kipindi chako (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Amri za Msingi

### Kumbukumbu (Memories)
Maelezo ya muktadha na uchunguzi uliohifadhiwa na Omi:

```bash
# Orodhesha kumbukumbu zilizohifadhiwa
omi memory list

# Unda kumbukumbu mpya
omi memory create "Anapendelea majibu mafupi ya kiufundi yenye mifano ya Python" --category work

# Pata kumbukumbu maalum kwa kitambulisho chake
omi memory get <MEMORY_ID>
```

### Mazungumzo (Conversations)
Mazungumzo yaliyorekodiwa na nakala za maandishi kutoka kwa vifaa vya Omi:

```bash
# Orodhesha mazungumzo 5 ya hivi karibuni
omi conversation list --limit 5

# Pata mazungumzo pamoja na nakala kamili ya maandishi
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Majukumu ya Kutenda (Action Items)
Majukumu yaliyotambuliwa kiotomatiki kutoka kwa mazungumzo:

```bash
# Orodhesha majukumu yaliyo wazi
omi action-item list --open

# Weka alama kuwa jukumu limekamilika
omi action-item complete <ACTION_ITEM_ID>
```

### Malengo (Goals)
Malengo ya muda mrefu na ufuatiliaji wa maendeleo:

```bash
# Orodhesha malengo yote yanayoendelea
omi goal list

# Unda lengo linalopimika kwa nambari
omi goal create "Kunywa lita 2 za maji kila siku" --type numeric --target 2 --unit liters
```

---

## 4. Mifumo ya Kiotomatiki na Matokeo ya JSON (`--json`)

`omi-cli` imeboreshwa kwa ajili ya hati za kiotomatiki na ujumuishaji wa mawakala wa AI. Bendera ya `--json` inatoa matokeo halali ya JSON yanayoweza kuchakatwa na zana kama `jq`:

```bash
# Orodhesha kumbukumbu katika umbizo la JSON na uchuje kwa kutumia jq
omi --json memory list | jq '.[] | {id, content, category}'

# Pata vichwa vya mazungumzo ya hivi karibuni
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Onyesha majukumu yaliyo wazi katika muundo ghafi wa JSON
omi --json action-item list --open | jq '.'
```

> **Kanuni Muhimu ya Sintaksia:**
> Bendera ya `--json` ni **chaguo la kimataifa**, kumaanisha lazima iwekwe **kabla** ya kitenzi cha amri ndogo:
> * Sahihi: `omi --json memory list`
> * Sio sahihi: `omi memory list --json`

### Mgawanyo wa Kurasa (Pagination) na Utoaji wa Faili
Tumia vigezo vya `--limit` na `--offset` kupitia kiasi kikubwa cha data:

```bash
# Gawanya matokeo kwa kurasa
omi --json memory list --limit 25 --offset 0 > kumbukumbu-ukurasa-1.json
omi --json memory list --limit 25 --offset 25 > kumbukumbu-ukurasa-2.json
```

---

## 5. Misimbo ya Kutoka (Exit Codes)

Misimbo thabiti ya kukamata hitilafu kwenye hati za kiotomatiki na michakato ya CI/CD:

| Msimbo | Jina la Msimbo | Maelezo |
| :---: | :--- | :--- |
| `0` | **`EXIT_OK`** | Amri imetekelezwa kikamilifu bila hitilafu yoyote. |
| `1` | **`EXIT_USAGE`** | Hitilafu ya matumizi au sintaksia, vigezo visivyo sahihi, au hoja zinazokosekana. |
| `2` | **`EXIT_AUTH`** | Hitilafu ya uthibitishaji, ufunguo uliokwisha muda, au ukosefu wa ruhusa. |
| `3` | **`EXIT_SERVER`** | Hitilafu ya seva (HTTP 5xx), hitilafu ya mtandao, au muda wa ombi kuisha. |
| `4` | **`EXIT_RATE_LIMITED`** | Hitilafu ya kuzidisha viwango vya maombi (HTTP 429). |
| `5` | **`EXIT_NOT_FOUND`** | Rasilimali iliyoombwa haipatikani kwenye seva (HTTP 404). |

---

## 6. Mifano ya Mazingira ya Kituo cha Amri

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_ufunguo_wako_hapa"

# Tekeleza amri na uangalie msimbo wa kutoka
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Hitilafu ilitokea wakati wa kupata kumbukumbu." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_ufunguo_wako_hapa"

# Badilisha matokeo ya JSON kuwa kifaa cha PowerShell moja kwa moja
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Angalia hitilafu kupitia $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Amri ya Omi imeshindwa na msimbo wa hitilafu: $LASTEXITCODE."
}
```

---

## 7. Muunganisho wa API ya Eneo-Kazi (Local Desktop API)

Ikiwa programu ya mezani ya Omi inafanya kazi kwenye kompyuta hiyo hiyo, unaweza kuuliza data ya skrini bila kupitia wingu:

```bash
# Weka anwani ya ndani na ishara ya ufikiaji
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Weka ishara ya ndani (token): " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Angalia hali ya huduma ya ndani
omi --json local status

# Tafuta kwenye kumbukumbu za skrini ya ndani
omi --json local search-screen "Ripoti ya robo mwaka" --days 7 --app Safari
```

---

## 8. Wasifu Nyingi (Profiles)

Bendera ya `--profile` inakuruhusu kutenganisha akaunti za kibinafsi, za kazi, au mazingira ya majaribio. Mipangilio huhifadhiwa katika `~/.omi/config.toml`:

```bash
# Sanidi na uingie kwenye wasifu binafsi
omi --profile personal auth login

# Sanidi na uingie kwenye wasifu wa kazi
omi --profile work auth login

# Tekeleza amri ukitumia wasifu maalum
omi --profile work memory list

# Tumia mazingira ya majaribio (staging)
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Usalama na Mbinu Bora

* **Usiweke Funguo kwenye Git:** Kamwe usitume funguo za siri za API kwenye mifumo ya umma ya Git. Tumia faili za mazingira zilizoorodheshwa kwenye `.gitignore`.
* **Linda Historia ya Terminal:** Kwenye mashine zinazotumiwa na watu wengi, epuka kuandika funguo za siri wazi kwenye mistari ya amri; tumia menyu ya maingiliano au vigezo vya mazingira kama `OMI_API_KEY`.
* **Ruhusa za Faili:** Kwenye mifumo inayotii Unix, weka ruhusa dhabiti kwa folda ya usanidi ya `~/.omi/` (`chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`).
