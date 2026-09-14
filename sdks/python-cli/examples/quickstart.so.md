# Hagaha bilowga degdegga ah ee omi-cli (Somali Quickstart)

> Hage wax ku ool ah oo lagu shaqeeyo Omi si toos ah terminal-ka — loogu talagalay horumariyeyaasha iyo wakiillada AI ee madaxa bannaan.

`omi-cli` waa command-line interface-ka rasmiga ah ee developer API-ga [Omi](https://omi.me). Wuxuu kuu oggolaanayaa inaad maamusho afarta qaybood ee aasaasiga ah ee nidaamka si habaysan oo si otomaatig ah loo samayn karo: xusuusaha (memories), wadahadallada (conversations), hawlaha la qabto (action items) iyo yoolalka (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dukumeentiyada rasmiga ah:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Koodhka isha:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Magacyada amarrada, doorashooyinka iyo fariimaha barnaamijka waxay ku sii jiraan Ingiriisi; qoraalka sharaxaadda ee hagahan oo keliya ayaa ku qoran Soomaali. README-ga Ingiriisiga ayaa ah tixraaca aasaasiga ah.

---

## 1. Rakibaadda

Si looga fogaado isku-dhacyada dependency-ga oo CLI-ga loogu shaqeeyo deegaan go'doonsan, waxaa lagula talinayaa `pipx`:

```bash
# La taliyey: rakibaad go'doonsan oo pipx ah
pipx install omi-cli

# Beddelka: pip gudaha Python virtual environment firfircoon
pip install omi-cli
```

> **Fiiro gaar ah: Magaca package-ka iyo magaca amarka**
> * Magaca package-ka ee PyPI waa **`omi-cli`** (magaca `omi` wuxuu leeyahay package aan la xiriirin).
> * Amarka aad terminal-ka ku shaqaysanayso waa **`omi`** oo keliya.

Xaqiiji in rakibaaddu shaqaynayso:

```bash
omi --version
omi --help
```

Haddii terminal-ku uusan helin `omi`, hubi in virtual environment-ku firfircoon yahay ama in faylka `pipx` ku dhigo faylasha la fulin karo uu ku jiro `PATH`-kaaga.

---

## 2. Xaqiijinta aqoonsiga (Authentication)

`omi-cli` wuxuu taageeraa laba hab oo aasaasi ah oo xaqiijin:

| Habka | Isticmaalka | Tusaale |
| :--- | :--- | :--- |
| **Furaha API ee horumariyaha (`omi_dev_*`)** | Script-yada, CI/CD, server-yada aan shaashad lahayn, wakiillada AI | `omi auth login --api-key ...` ama `OMI_API_KEY` |
| **OAuth-ka browser-ka (Google/Apple)** | Goobaha shaqada ee maxalliga ah iyo horumariyeyaasha | `omi auth login --browser` (Google) / `--provider apple` |

### Gelitaan is-dhexgal ah
Ku shaqee adigoon flag lahayn si aad habka u doorato si is-dhexgal ah:

```bash
omi auth login
# 1) Browser — wuxuu furayaa browser-ka gelitaanka Google (u isticmaal `--provider apple` Apple)
# 2) API key — ku dheji furaha API ee app.omi.me (gelinta waa la qariyey)
```

### Gelitaan toos ah oo browser ah
```bash
# Caadiga: gelitaanka Google
omi auth login --browser

# Beddelka: gelitaanka Apple
omi auth login --browser --provider apple
```

### Isticmaalka furaha API ee horumariyaha
Ku samee fure [app.omi.me](https://app.omi.me) hoosta **Developer → API Keys**:

```bash
# Ku kaydi furaha profile-ka maxalliga ah ee firfircoon
omi auth login --api-key omi_dev_token_kaaga_dhabta_ah

# Ama u dhig environment variable (ugu fiican container-ada iyo CI/CD)
export OMI_API_KEY="omi_dev_token_kaaga_dhabta_ah"
```

> `OMI_API_KEY` waxaa la isticmaalaa oo keliya marka profile-ka firfircoon uusan lahayn fure la kaydiyey. Haddii aad horey ugu gashay `omi auth login` oo aad rabto in environment variable-ku shaqeeyo, marka hore ku shaqee `omi auth logout`.

### Hubinta xaaladda xaqiijinta
* `omi auth status`: wuxuu muujiyaa profile-ka firfircoon iyo aqoonsiga la qariyey (wuxuu ku shaqeeyaa maxalli ahaan/offline; taariikhda dhicitaanku waxay khusaysaa oo keliya token-nada OAuth).
* `omi auth whoami`: wuxuu codsi u diraa server-ka Omi si uu u xaqiijiyo ansaxnimada (wuxuu u baahan yahay shabakad).

```bash
omi auth status
omi auth whoami
```

Cusboonaysii token-ka OAuth adigoon mar kale gelin:

```bash
omi auth refresh
```

> `omi auth refresh` wuxuu u shaqeeyaa oo keliya profile-yada ku galay browser-ka (OAuth). Profile-yada ku salaysan furaha API waxba lama cusboonaysiin karo, amarkuna wuxuu ku dhammaadaa fariinta «Nothing to refresh» iyo exit code `1`.

Ka bixitaanka:
```bash
omi auth logout
# Haddii OMI_API_KEY lagu dhigay environment-ka, isagana ka saar (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Amarrada aasaasiga ah

### Xusuusaha (Memories)
Xaqiiqooyin habaysan iyo indha-indhayn xaalad ah oo Omi kaydiyey:

```bash
# Liis gareey xusuusaha
omi memory list

# Samee xusuus cusub oo qayb leh
omi memory create "Waxaan door bidaa jawaabo farsamo oo kooban oo leh tusaalooyin Python ah" --category work

# Soo qaad xusuus gaar ah adigoo isticmaalaya ID
omi memory get <MEMORY_ID>
```

### Wadahadallada (Conversations)
Duubista codka, qoraallada iyo wadahadallada ay diiwaangeliyeen qalabka Omi:

```bash
# Liis gareey 5-ta wadahadal ee ugu dambeeyay
omi conversation list --limit 5

# Soo qaad faahfaahinta wadahadal oo ay ku jirto qoraalka oo dhan
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Hawlaha la qabto (Action Items)
Hawlo si otomaatig ah looga soo saaray wadahadallada:

```bash
# Liis gareey hawlaha furan
omi action-item list --open

# Calaamadee hawl inay dhammaatay
omi action-item complete <ACTION_ITEM_ID>
```

### Yoolalka (Goals)
Tilmaamayaasha horumarka iyo yoolalka muddada dheer:

```bash
# Liis gareey yoolalka firfircoon
omi goal list

# Samee yool tiro ah oo cusub
omi goal create "Cab 2 litir oo biyo ah maalin kasta" --type numeric --target 2 --unit liters

# Cusboonaysii qiimaha hadda ee yool (ID iyo qiimaha cusub)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. Otomaatig habaysan iyo wax-soo-saarka JSON (`--json`)

`omi-cli` waxaa loo dhisay otomaatig gudaha pipeline-yada iyo toolchain-yada. Flag-ga guud ee `--json` wuxuu soo celiyaa JSON nadiif ah oo mashiin akhriyi karo:

```bash
# Liis gareey xusuusaha JSON ahaan oo ku shaandhee jq
omi --json memory list | jq '.[] | {id, content, category}'

# Soo qaad cinwaanada wadahadallada dhawaan
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Eeg dhammaan hawlaha furan JSON ceyriin ahaan
omi --json action-item list --open | jq '.'
```

> **Xeer muhiim ah oo syntax ah:**
> `--json` waa **doorasho guud** waana in la dhigaa subcommand-ka **ka hor**:
> * Sax: `omi --json memory list`
> * Khalad: `omi memory list --json`

### Bog-u-kala-qaybinta (Pagination)
Amarrada `list` waxay taageeraan `--limit` iyo `--offset`:

```bash
omi --json memory list --limit 50 --offset 50
```

### U dhoofinta fayl
Si ay midabada ANSI ama xarfaha xakamaynta uusan u wasakhayn faylka, si toos ah ugu jihee stdout gudaha shell-ka:

```bash
# U dhoofi xusuusaha si toos ah fayl JSON nadiif ah
omi --json memory list > memories.json
```

---

## 5. Koodhadhka ka-bixitaanka (Exit Codes Contract)

Si loo helo maaraynta khaladaadka oo lagu kalsoonaan karo CI/CD iyo script-yada, `omi-cli` wuxuu raacaa heshiis adag oo koodhadhka ka-bixitaanka ah (eeg `omi_cli/errors.py`):

| Koodh | Magac | Sharaxaad iyo tusaale |
| :---: | :--- | :--- |
| `0` | **Guul (`EXIT_OK`)** | Hawshu waxay dhammaatay khalad la'aan. |
| `1` | **Khalad isticmaal (`EXIT_USAGE`)** | Khaladaadka xaqiijinta ee omi-cli laftiisa: `--browser` iyo `--api-key` oo aan la isku dari karin, doorasho aan sax ahayn gelitaanka is-dhexgalka ah, gelin madhan oo stdin ah, ama `omi auth refresh` profile fure API ah. |
| `2` | **Khalad xaqiijin (`EXIT_AUTH`)** | Aqoonsi maqan ama aan sax ahayn, ama fadhi dhacay. Fiiro gaar ah: flag aan la aqoon ama argument maqan ayaa Click laftiisu diidaa oo sidoo kale ku baxa koodhka `2`. |
| `3` | **Khalad server (`EXIT_SERVER`)** | HTTP 5xx oo ka yimid server-ka Omi ama kala go' shabakad. |
| `4` | **Xaddidaadda heerka (`EXIT_RATE_LIMITED`)** | HTTP 429 — codsiyo aad u badan muddo gaaban. |
| `5` | **Lama helin (`EXIT_NOT_FOUND`)** | HTTP 404 — kheyraadka la codsaday (xusuus, wadahadal, hawl) ma jiro. |

---

## 6. Tusaalooyin shell-yo kala duwan

### Bash / Zsh (Linux / macOS)
```bash
# Dhig furaha API ee fadhigan
export OMI_API_KEY="omi_dev_token_kaaga_dhabta_ah"

# Ku shaqee amarka oo hubi koodhka ka-bixitaanka
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Khalad ayaa dhacay markii xusuusaha laga soo qaadayay Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# Qeex environment variable gudaha PowerShell
$env:OMI_API_KEY = "omi_dev_token_kaaga_dhabta_ah"

# U beddel wax-soo-saarka JSON si toos ah PowerShell object
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Hubi khaladka adigoo isticmaalaya $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Amarka Omi wuu fashilmay koodhka ka-bixitaanka $LASTEXITCODE."
}
```

---

## 7. Isku-dhafka API-ga Desktop-ka maxalliga ah (Omi Desktop)

Marka Omi Desktop uu ku shaqaynayo mashiinkaaga (port-ka caadiga ah 47778), waxaad si toos ah ula shaqayn kartaa xaaladda maxalliga ah adigoon cloud-ka marin:

```bash
# Habee isku-xirka API-ga maxalliga ah (isticmaal environment variables si aad token-ka u ilaaliso)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Geli token-ka Desktop: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Xaqiiji xaaladda isku-xirka maxalliga ah
omi --json local status

# Ka raadi taariikhda shaashadda maxalliga ah
omi --json local search-screen "Warbixinta rubuc-sannadeedka" --days 7 --app Safari
```

Halkii environment variables, waxaad dejinta ku kaydin kartaa profile-ka: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Maaraynta profile-yo badan (Profiles)

Isticmaal `--profile` si aad si fudud ugu kala beddesho akoonka shakhsiga ah, profile-ka shaqada ama deegaanka tijaabada. Dejintu waxay ku kaydsan tahay `~/.omi/config.toml`. Kala horraynta mudnaanta: flag-ga `--profile`, kadib environment variable-ka `OMI_PROFILE`, ugu dambayntiina profile-ka `default`.

```bash
# Samee oo gal profile-ka shakhsiga ah
omi --profile personal auth login

# Samee oo gal profile-ka shaqada
omi --profile work auth login

# Ku shaqee amar profile gaar ah
omi --profile work memory list

# Dooro profile-ka adigoo isticmaalaya environment variable
export OMI_PROFILE=work
omi memory list

# U isticmaal endpoint gaar ah tijaabada
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Tilmaamaha amniga iyo hab-dhaqanka ugu fiican

* **Furayaasha koodhka ha ku qorin:** Weligaa furayaasha API (`omi_dev_*`) ha ku samayn commit Git repository. Isticmaal faylasha `.env` ee ku jira `.gitignore` ama maamulayaasha sirta ee ammaan ah.
* **Ilaali taariikhda shell-ka:** Server-yada la wadaago, furayaasha ha u gudbin argument-yo command-line oo cad; isticmaal gelitaanka is-dhexgalka ah ama `OMI_API_KEY`.
* **Xaddid ogolaanshaha faylka:** Unix/macOS, hubi in faylka habaynta uu leeyahay ogolaansho xaddidan:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Nadiifinta fadhiga:** Marka aad burburinayso deegaannada ku-meel-gaarka ah, xusuusnow inaad ka saarto environment variable-ka:
  ```bash
  unset OMI_API_KEY
  ```
