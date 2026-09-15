# omi-cli — Hagaha Bilowga Degdegga ah ee Af-Soomaaliga (Somali Quickstart)

> Tilmaame wax ku ool ah oo lagula shaqeynayo Omi adoo adeegsanaya terminal-ka. Waxaa loogu talagalay dadka iyo wakiillada AI (AI agents).

`omi-cli` waa macmiilka rasmiga ah ee khadka taliska (CLI) ee loogu talagalay API-ga horumariyeyaasha [Omi](https://omi.me). Waxay ku siinaysaa marin toos ah oo qoraal ahaan loo maareyn karo afar qaybood oo muhiim ah: xusuuso (memories), wada-hadallo (conversations), tallaabooyinka hawsha (action items), iyo yoolal (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dukumentiyada Rasmiga ah:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Koodhka Isha (Source Code):** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Rakibaadda (Installation)

Habka ugu habboon ee la taliyo waa `pipx`: waxay ku rakibaysaa aaladda jawi gooni ah si aysan xirmooyinkeeda khilaaf u gelin mashaariicdaada kale:

```bash
# Habka la taliyo: rakibaadda adoo adeegsanaya pipx
pipx install omi-cli

# Ama adoo adeegsanaya pip
pip install omi-cli
```

> **Muhiim: Magaca xirmada iyo magaca amarka way kala duwan yihiin.**
> * Xirmada la rakibayo waa **`omi-cli`** (xirmada goonida ah ee `omi` waa mashruuc kale oo aan shaqo ku lahayn kan).
> * Rakibaadda ka dib, waxaad terminal-ka ka maamulaysaa amarka **`omi`**.

Hubi in wax walba si fiican u shaqeynayaan:

```bash
omi --version
omi --help
```

---

## 2. Xaqiijinta iyo Galitaanka (Authentication)

`omi-cli` waxay taageertaa laba hab oo loo galo:

| Habka | Ku habboon | Amarka |
| :--- | :--- | :--- |
| **Furaha Horumariyaha (`omi_dev_*`)** | CI/CD, qoraallada iswada, wakiillada AI | `omi auth login --api-key ...` ama doorsoomaha jawiga |
| **Galitaanka Bog-furaha (Google/Apple)** | Isticmaalka kombiyuutarkaaga shakhsiga ah | `omi auth login --browser` |

### Galitaanka Falgalka leh (Interactive login)

Haddii aad amarka fuliso adigoon calan raacinin, wuxuu ku weydiinayaa habka aad doorbideyso:

```bash
omi auth login
# 1) Browser — ku gal Google ama Apple (u fudud bini'aadamka)
# 2) API key — geli furaha horumariyaha ee aad ka heshay app.omi.me (u fudud wakiillada iyo CI)
```

Markaad doorato furaha API, wax gelinta waa la qariyaa si furahaagu uusan ugu harin taariikhda terminal-ka.

### Toos ugu gal bog-furaha (Browser)

```bash
omi auth login --browser
```

Apple ahaan:

```bash
omi auth login --browser --provider apple
```

### Ku gal furaha horumariyaha (API key)

Furaha waxaad ka heli kartaa [app.omi.me](https://app.omi.me) qaybta **Developer → API Keys**.

```bash
# Ku keydi furaha qaabeynta gudaha
omi auth login --api-key "omi_dev_furahaaga_halkan"

# Ama u gudbi ahaan doorsoomaha jawiga — habka ugu wanaagsan ee CI/CD iyo weelasha (containers)
export OMI_API_KEY="omi_dev_furahaaga_halkan"
```

Doorsoomaha jawiga `OMI_API_KEY` waxaa la adeegsadaa marka uusan fure ku keydsaneyn astaanta firfircoon, taasoo ka dhigan in weelasha aysan u baahnayn in wax lagu qoro disk-ga.

### Hubinta xaaladda galitaanka

Laba amar ayaa bixiya macluumaad kala duwan, waana inaan la isku khaldin:

* `omi auth status` — waxay hubisaa waxa yaalla **gudaha kombiyuutarkaaga (offline)**: astaanta, furaha la qariyay, iyo waqtiga dhicitaanka. Uma baahna internet.
* `omi auth whoami` — waxay la xiriirtaa **server-ka Omi**: waxay xaqiijisaa in furuhu shaqeynayo oo uu ansax yahay. Waxay u baahan tahay internet.

```bash
omi auth status    # Hubinta gudaha, offline
omi auth whoami    # Hubinta server-ka
```

Si aad u cusbooneysiiso furaha galitaanka ee dhacaya adigoon dib u gelin (kaliya galitaanka bog-furaha):

```bash
omi auth refresh
```

Ka bax:

```bash
# Ka bax astaanta
omi auth logout

# Haddii furaha API laga dhigay doorsoomaha jawiga, tirtir si aysan u sii shaqeyn
unset OMI_API_KEY
```

---

## 3. Awaamiirta Muhiimka ah

### Xusuusaha (Memories)

Xaqiiqooyinka iyo xogta uu nidaamku kaa xusuusto:

```bash
# Liiska xusuusaha
omi memory list

# Samee xusuus cusub
omi memory create "Adeegsaduhu wuxuu doorbidaa qaabka madow (dark theme)" --category lifestyle

# Eeg xusuus gaar ah
omi memory get <MEMORY_ID>
```

### Wada-hadallada (Conversations)

Taariikhda codka iyo qoraalka ee ka timid aaladda ama app-ka:

```bash
# 5-ta wada-hadal ee ugu dambeeyay
omi conversation list --limit 5

# Wada-hadal buuxa oo leh qoraalkiisa (transcript)
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Tallaabooyinka Hawsha (Action Items)

Hawlaha iyo waajibaadka uu Omi ka soo saaray wada-hadallada:

```bash
# Kaliya kuwa furan
omi action-item list --open

# Ku calaamadee mid la dhammeeyay
omi action-item complete <ACTION_ITEM_ID>
```

### Yoolalka (Goals)

Qorshayaasha iyo yoolalka muddada fog:

```bash
# Liiska yoolalka
omi goal list

# Diiwaangeli horumarka yoolka (waxay u baahan tahay labada doodood: yoolka iyo qiimaha)
omi goal progress <GOAL_ID> 25

# Taariikhda isbeddelka yoolka
omi goal history <GOAL_ID>
```

---

## Weydii Omi adoo adeegsanaya ereyadaada (`ask`)

Amarka heerka sare ah ee gaarka ah: wuxuu ku weydiinayaa su'aal luuqad dabiici ah, jawaabtana wuxuu ka dhisayaa wada-hadalladaadii hore:

```bash
omi ask "muxuu ahaa go'aankii aan ka gaaray qorshaha safarka"
omi --json ask "maxay ahaayeen hawlihii aan ballanqaaday inaan dhammeeyo usbuucan"
```

---

## 4. Qoraallada Iswada iyo JSON (`--json`)

Wakiillada AI iyo qoraallada shaqada (scripts), `omi-cli` waxay soo saari kartaa JSON mashiinku akhrisan karo. Calanka `--json` waa mid **caalami ah (global)** waana in la dhigaa **ka hor** amarka hoose.

```bash
# Xusuusaha: soo saar id iyo content (bogga 1-aad)
omi --json memory list | jq '.[] | {id, content}'

# Xusuusaha: u gudub bogagga xiga adoo adeegsanaya pagination (--limit iyo --offset)
omi --json memory list --limit 25 --offset 25 | jq '.[] | {id, content}'

# Cinwaannada wada-hadalladii ugu dambeeyay
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Tallaabooyinka hawsha ee furan
omi --json action-item list --open | jq '.'
```

> **Qalad caadi ah:** `--json` waa inay ka horreysaa amarka hoose, ee kama dambeyso.
> * Sax: `omi --json memory list`
> * Qalad: `omi memory list --json`

---

## 5. Heshiiska Xeerarka Ka Bixitaanka (Exit Codes Contract)

Xeerarka ka bixitaanka waxay si adag ugu xiran yihiin qandaraaska lagu qeexay [omi_cli/errors.py](https://github.com/BasedHardware/omi/blob/main/sdks/python-cli/omi_cli/errors.py), si qoraallada iyo CI ay ugu kalsoonaadaan:

| Koodhka | Magaca Astaanta ah | Micnaha iyo Xaaladda |
| :---: | :--- | :--- |
| **0** | `EXIT_OK` | Guul — Amarku si buuxda ayuu u guuleystay |
| **1** | `EXIT_USAGE` | Khalad isticmaal — Amar aan sax ahayn, doodo maqan, ama xaqiijin fashilantay |
| **2** | `EXIT_AUTH` | Khalad aqoonsi — Furaha API oo maqan, dhacay, ama aan fasax lahayn |
| **3** | `EXIT_SERVER` | Khaladka server-ka ama xiriirka — Jawaabta 5xx ama xiriirku go'an yahay |
| **4** | `EXIT_RATE_LIMITED` | Xadka codsiyada oo la dhaafay — HTTP 429 Too Many Requests |
| **5** | `EXIT_NOT_FOUND` | Lama helin — Khayraadka (ID) la codsaday ma jiro (HTTP 404) |

Tusaalaha maareynta qaladka ee Bash:

```bash
omi --json memory list > /dev/null 2>&1
EXIT_CODE=$?
if [ "$EXIT_CODE" -ne 0 ]; then
  case $EXIT_CODE in
    1) echo "Khalad: Isticmaal aan sax ahayn ama calan khaldan." ;;
    2) echo "Khalad: Aqoonsigu wuu fashilmay. Fadlan orod 'omi auth login'." ;;
    3) echo "Khalad: Server-ka ayaa cilad qaba ama xiriirka ayaa go'an." ;;
    4) echo "Khalad: Xadka codsiyada waa la dhaafay. Fadlan wax yar sug." ;;
    5) echo "Khalad: Khayraadka lama helin." ;;
    *) echo "Khalad: Dhibaato lama filaan ah oo wadata koodhka $EXIT_CODE." ;;
  esac
  exit $EXIT_CODE
fi
```

---

## 6. Isticmaalka Sare: API-ga Maxalliga ah iyo Astaamo Badan

### Isku xirka API-ga Desktop-ka ee Maxalliga ah

Marka uu app-ka Omi Desktop ka shaqeynayo kombiyuutarkaaga, waxaad toos ugu xirmi kartaa halkii aad daruurta (cloud) aadi lahayd:

```bash
# U qoondee cinwaanka maxalliga ah
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"

# Deji furaha maxalliga ah
export OMI_LOCAL_TOKEN="furahaaga_maxalliga_ah"

# Hubi xaaladda maxalliga ah
omi local status
```

### Maareynta Astaamaha Badan (Multi-profile)

Waxaad u keydsan kartaa astaamo gooni ah jawiyada kala duwan (tusaale, shakhsi, shaqo, ama tijaabo):

```bash
# Ku gal astaanta tijaabada (staging)
omi --profile staging auth login --api-key "omi_dev_staging_key"

# Ku orod amarka astaanta tijaabada
omi --profile staging memory list
```

---

## 7. Soo Koobid

`omi-cli` waxay horumariyeyaasha iyo wakiillada AI siisaa awoodda buuxda ee xogta Omi iyadoo toos looga maamulayo terminal-ka. Faahfaahin dheeraad ah iyo dukumentiyada Python SDK, booqo [docs.omi.me](https://docs.omi.me).
