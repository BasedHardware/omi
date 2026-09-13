# omi-cli Treoir Mearthosaithe (Irish Quickstart)

> Treoir phraiticiúil chun Omi a úsáid go díreach ón teirminéal — cruthaithe d'fhorbróirí agus do ghníomhairí uathrialacha AI.

Is é `omi-cli` an comhéadan líne ordaithe (CLI) oifigiúil do API forbróra [Omi](https://omi.me). Soláthraíonn sé rochtain struchtúrtha ar na 4 phríomhacmhainn de chuid Omi: cuimhní (memories), comhráite (conversations), míreanna gníomhaíochta (action items), agus spriocanna (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Doiciméadúchán oifigiúil:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Cód foinse:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Suiteáil

Chun coinbhleachtaí idir spleáchais chórais a sheachaint agus timpeallacht scoite a chothabháil, moltar go mór `pipx` a úsáid:

```bash
# Modh molta: suiteáil scoite trí pipx
pipx install omi-cli

# Suiteáil mhalartach trí pip caighdeánach (m.sh. i dtimpeallacht fhíorúil)
pip install omi-cli
```

> **Soiléiriú tábhachtach: Ainm an phacáiste i gcomparáid le hainm an ordaithe**
> * Is é **`omi-cli`** ainm oifigiúil an phacáiste ar PyPI (is tionscadal ar leith agus neamhghaolmhar é an pacáiste `omi`).
> * Is é **`omi`** go díreach an t-ordú a ritear sa teirminéal.

Deimhnigh gur éirigh leis an tsuiteáil tríd an leagan agus an roghchlár cabhrach a thaispeáint:

```bash
omi --version
omi --help
```

---

## 2. Fíordheimhniú (Authentication)

Tacaíonn `omi-cli` le dhá phríomh-mhodh fíordheimhnithe:

| Modh | Feidhm | Sampla ordaithe |
| :--- | :--- | :--- |
| **Eochair API Forbróra (`omi_dev_*`)** | Uathoibriú, CI/CD, freastalaithe gan ceann (headless), gníomhairí AI | `omi auth login --api-key ...` nó `OMI_API_KEY` |
| **Logáil isteach OAuth trí bhrabhsálaí (Google/Apple)** | Forbairt áitiúil ar ríomhaire pearsanta | `omi auth login --browser` (Google) / `--provider apple` |

### Logáil isteach idirghníomhach
Nuair a ritheadh an t-ordú gan paraiméadair bhreise, cuirtear tús le roghchlár idirghníomhach a cheiltíonn d'eochair le linn iontrála:

```bash
omi auth login
# 1) Browser — Logáil isteach le Google tríd an mbrabhsálaí (le haghaidh Apple, úsáid an bratach `--provider apple`)
# 2) API key — Greamaigh eochair API forbróra ó app.omi.me
```

### Logáil isteach go díreach tríd an mbrabhsálaí
```bash
# Gnáthlogáil isteach le cuntas Google
omi auth login --browser

# Logáil isteach mhalartach le próifíl Apple
omi auth login --browser --provider apple
```

### Logáil isteach le heochair API forbróra
Gin eochair API ó dheais [app.omi.me](https://app.omi.me) faoin rannóg **Developer → API Keys**:

```bash
# Sábháil an eochair sa phróifíl áitiúil reatha
omi auth login --api-key omi_dev_...

# Nó trí athróg thimpeallachta a easpórtáil (an-oiriúnach do choimeádáin Docker agus CI/CD):
export OMI_API_KEY="omi_dev_d_eochair_anseo"
```

> **Nóta tosaíochta agus slándála dintiúr:**
> * Má tá eochair shábháilte sa phróifíl ghníomhach cheana féin, tugtar tosaíocht di thar an athróg thimpeallachta `OMI_API_KEY`. Rith `omi auth logout` ar dtús más mian leat an athróg a úsáid.
> * Seachain an eochair a chur go díreach mar argóint líne ordaithe ar mheaisíní roinnte ionas nach sábhálfar í i stair an teirminéil.

### Seiceáil stádas an fhíordheimhnithe
* `omi auth status`: Taispeánann sé an phróifíl ghníomhach agus aitheantóir faoi mhasc gan iarratas líonra (oibríonn sé as líne).
* `omi auth whoami`: Seolann sé iarratas bailíochtaithe chuig freastalaí Omi chun bailíocht an tseisiúin a dhearbhú (teastaíonn nasc idirlín).

```bash
omi auth status
omi auth whoami
```

### Logáil amach (Logout)
```bash
omi auth logout
# Má d'úsáid tú an athróg thimpeallachta OMI_API_KEY, bain den seisiún í:
unset OMI_API_KEY
```

---

## 3. Príomhorduithe

### Cuimhní (Memories)
Nótaí comhthéacsúla agus tuairimí a thaifeadann Omi:

```bash
# Liosta de na cuimhní sábháilte a thaispeáint
omi memory list

# Cuimhne nua a chruthú
omi memory create "Is fearr leis freagraí gonta teicniúla le samplaí Python" --category work

# Cuimhne ar leith a fháil de réir aitheantais
omi memory get <MEMORY_ID>
```

### Comhráite (Conversations)
Comhráite taifeadta agus tras-scríbhinní ó ghléasanna Omi:

```bash
# Liosta de na 5 chomhrá is déanaí
omi conversation list --limit 5

# Comhrá a fháil mar aon leis an tras-scríbhinn iomlán
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Míreanna gníomhaíochta (Action Items)
Tascanna a aithníodh go huathoibríoch ó chomhráite:

```bash
# Míreanna gníomhaíochta oscailte a thaispeáint
omi action-item list --open

# Mír ghníomhaíochta a mharcáil mar chomhlánaithe
omi action-item complete <ACTION_ITEM_ID>
```

### Spriocanna (Goals)
Spriocanna fadtéarmacha agus rianú ar dhul chun cinn:

```bash
# Liosta de na spriocanna gníomhacha
omi goal list

# Sprioc chainníochtúil a chruthú
omi goal create "Ól 2 lítear uisce gach lá" --type numeric --target 2 --unit liters
```

---

## 4. Uathoibriú struchtúrtha agus aschur JSON (`--json`)

Tá `omi-cli` optamaithe le haghaidh comhtháthú scripteanna agus gníomhairí AI. Tugann an bratach uilíoch `--json` formáid JSON bhailí ar ais le haghaidh próiseála le huirlisí cosúil le `jq`:

```bash
# Liosta cuimhní i bhformáid JSON agus scagadh le jq
omi --json memory list | jq '.[] | {id, content, category}'

# Teidil na gcomhráite is déanaí a fháil
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Míreanna gníomhaíochta oscailte a thaispeáint i bhfoirm JSON amh
omi --json action-item list --open | jq '.'
```

> **Riail thábhachtach maidir le comhréir:**
> Is **rogha uilíoch (global option)** é an bratach `--json`, rud a chiallaíonn nach mór é a chur **roimh** an bhfor-ordú:
> * Ceart: `omi --json memory list`
> * Mícheart: `omi memory list --json`

### Leathanú agus easpórtáil chuig comhaid
Úsáid na paraiméadair `--limit` agus `--offset` chun dul trí mhéideanna móra sonraí:

```bash
# Leathanú ar na torthaí
omi --json memory list --limit 25 --offset 0 > cuimhni-leathanach-1.json
omi --json memory list --limit 25 --offset 25 > cuimhni-leathanach-2.json
```

Athscríobhann nó cruthaíonn an t-atreorú an comhad go háitiúil. Deimhnigh cód scoir an ordaithe i gcónaí sula ndéanann tú na sonraí a phróiseáil. Seoltar earráidí chuig an ngnáthshruth earráide (stderr), mar sin ní ráthaíocht é comhad folamh nach bhfuil aon sonraí ann. D'fhéadfadh sonraí pearsanta a bheith i gcomhaid easpórtáilte — cosain iad de réir do bheartas slándála.

---

## 5. Cóid scoir (Exit Codes)

Láimhseáil iontaofa earráidí i scripteanna CLI agus i bpíblínte CI/CD de réir chonradh `omi_cli/errors.py`:

| Cód | Brí | Cur síos |
| :---: | :--- | :--- |
| `0` | **Rath (`EXIT_OK`)** | D'éirigh leis an ordú gan earráidí. |
| `1` | **Earráid úsáide / chomhréire (`EXIT_USAGE`)** | Luachanna neamhbhailí, teipeanna bailíochtaithe feidhmchláir, nó argóintí ar iarraidh. |
| `2` | **Earráid fhíordheimhnithe (`EXIT_AUTH`)** | Dintiúir ar iarraidh, eochair imithe as feidhm, nó ceadanna neamhdhóthanacha (nó earráid anailíseora Click). |
| `3` | **Earráid freastalaí nó líonra (`EXIT_SERVER`)** | Freagra HTTP 5xx, teip cheangail líonra, nó teorainn ama iarratais (timeout). |
| `4` | **Ráta-theorannaithe (`EXIT_RATE_LIMITED`)** | Freagra HTTP 429 — an iomarca iarratas i dtréimhse ghearr ama. |
| `5` | **Acmhainn gan aimsiú (`EXIT_NOT_FOUND`)** | Freagra HTTP 404 — níl an réad nó an t-aitheantas a iarradh ann. |

---

## 6. Samplaí do thimpeallachtaí teirminéil éagsúla

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_d_eochair_anseo"

# Rith ordú agus deimhnigh an cód scoir
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Tharla earráid agus cuimhní á bhfáil (cód scoir: $?)." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_d_eochair_anseo"

# Aschur JSON a thiontú go díreach ina réad PowerShell
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Seiceáil le haghaidh earráide trí $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Chríochnaigh ordú Omi le cód earráide: $LASTEXITCODE."
}
```

### Windows Command Prompt (`cmd.exe`)
```cmd
set OMI_API_KEY=omi_dev_d_eochair_anseo

omi --json memory list --limit 10
if %ERRORLEVEL% neq 0 (
    echo Tharla earraid agus cuimhni a bhfail (cod scoir: %ERRORLEVEL%). >&2
)
```

---

## 7. Comhtháthú leis an bhfeidhmchlár deisce áitiúil (Local Desktop API)

Má tá feidhmchlár deisce Omi ag rith ar an meaisín céanna, is féidir leat ceisteanna a chur ar stair scáileáin áitiúil gan rochtain ar an néal:

```bash
# Seoladh áitiúil agus comhartha rochtana (token) a shocrú
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Iontráil an comhartha deisce: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Seiceáil stádas na seirbhíse áitiúla
omi --json local status

# Cuardach i stair an scáileáin
omi --json local search-screen "Tuarascáil Ráithiúil" --days 7 --app Safari
```

---

## 8. Próifílí iolracha a úsáid (Profiles)

Ligeann an bratach `--profile` duit cuntais phearsanta, oibre, nó timpeallachtaí tástála a choinneáil ar leithligh. Stóráiltear an chumraíocht i `~/.omi/config.toml`:

```bash
# Próifíl phearsanta a chruthú agus logáil isteach inti
omi --profile personal auth login

# Próifíl oibre a chruthú agus logáil isteach inti
omi --profile work auth login

# Ordú a rith le próifíl ar leith
omi --profile work memory list

# Úsáid timpeallacht tástála (staging)
omi --profile staging config set api_base https://api.staging.omi.me
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Slándáil agus dea-chleachtais

* **Ná cuir eochracha i Git:** Ná cuir eochracha API i stórtha poiblí riamh; bain úsáid as bainisteoir rúin nó comhaid timpeallachta atá liostaithe in `.gitignore`.
* **Cosaint staire an teirminéil:** Ar mheaisíní roinnte, seachain eochracha a chur mar pharaiméadair orduithe; bain úsáid as an logáil isteach idirghníomhach nó an athróg thimpeallachta `OMI_API_KEY`.
* **Ceadanna comhaid:** I dtimpeallachtaí Unix, socraigh ceadanna sriantacha ar an eolaire cumraíochta agus ar an gcomhad cumraíochta:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml
  ```
