# Treoir Mhearthosaithe do omi-cli (Gaeilge)

Is comhéadan líne ordaithe (CLI) oifigiúil é `omi-cli` chun idirghníomhú le héiceachóras Omi: rochtain a fháil ar chuimhní (memories), comhráite (conversations), gníomhartha (action items), agus spriocanna (goals). Tá an treoir seo scríofa go heisiach i nGaeilge do thimpeallachtaí uathoibrithe, oibreoirí teirminéil, agus forbróirí.

---

## 1. Suiteáil (Installation)

Dáiltear an pacáiste ar PyPI faoin ainm `omi-cli`. Nuair a bheidh sé suiteáilte, cuirtear an t-ordú `omi` ar fáil ar do `$PATH`:

```bash
# Modh molta: suiteáil aonraithe trí pipx
pipx install omi-cli

# Nó trí ghnáth-pip:
pip install omi-cli
```

Deimhnigh an tsuiteáil trí leagan agus cabhair an uirlis a sheiceáil:

```bash
omi --version
omi --help
```

> **Nóta:** Is é `omi-cli` ainm an phacáiste ar PyPI (toisc go bhfuil an focal `omi` ina aonar in úsáid ag pacáiste neamhghaolmhar), ach is é `omi` ainm an ordaithe i gcónaí.

---

## 2. Fíordheimhniú (Authentication)

Tacaíonn `omi-cli` le fíordheimhniú idirghníomhach trí bhrabhsálaí agus le heochracha API forbróra.

```bash
omi auth login
# 1) Browser — Logáil isteach trí bhrabhsálaí (Google nó Apple)
# 2) API key — Eochair forbróra ó app.omi.me a ghreamú
```

### Logáil isteach trí bhrabhsálaí gréasáin

```bash
# Logáil isteach le cuntas Google (réamhshocrú)
omi auth login --browser

# Logáil isteach le cuntas Apple
omi auth login --browser --provider apple
```

### Logáil isteach le heochair API forbróra

Gin eochair API ar phainéal rialaithe [app.omi.me](https://app.omi.me) faoin rannóg **Developer → API Keys**:

```bash
# Sábháil an eochair sa phróifíl ghníomhach áitiúil
omi auth login --api-key omi_dev_bhur_gcuid_eochrach_anseo

# Nó socrú mar athróg thimpeallachta (molta do choimeádáin Docker agus próisis CI/CD):
export OMI_API_KEY="omi_dev_bhur_gcuid_eochrach_anseo"
```

> **Nóta slándála agus tosaíochta:**
> * Fágann úsáid an bhrataigh `--api-key` go díreach ar an líne ordaithe an eochair le feiceáil i stair an bhlaoisc (`shell history`) agus i dblaosc na bpróiseas córais. Ar mheaisíní roinnte, is fearr greamú idirghníomhach (`omi auth login`) nó an athróg thimpeallachta `OMI_API_KEY`.
> * Má tá eochair shábháilte ag an bpróifíl ghníomhach sa chumraíocht cheana féin, tá tosaíocht aici ar an athróg thimpeallachta. Chun `OMI_API_KEY` a úsáid, déan logáil amach ar dtús le `omi auth logout` nó úsáid próifíl nua.

### Fíorú stádas an tseisiúin

* `omi auth status`: Taispeánann sé an phróifíl ghníomhach agus an t-aitheantóir masctha ón gcumraíocht áitiúil (oibríonn sé as líne).
* `omi auth whoami`: Seolann sé iarratas líonra chuig freastalaithe Omi chun bailíocht an tseisiúin a dheimhniú.

```bash
omi auth status
omi auth whoami
```

### Logáil amach (Logout)

Chun dintiúir atá stóráilte go háitiúil a ghlanadh:

```bash
omi auth logout
# Má d'úsáid tú an athróg thimpeallachta OMI_API_KEY, bain den seisiún í:
unset OMI_API_KEY
```

> **Nóta slándála comhaid:** Stóráiltear an chumraíocht i `~/.omi/config.toml`. Ar chórais Unix/Linux, moltar ceadanna dochta a shocrú: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Príomhorduithe

### Cuimhní (Memories)

Fíricí, breathnuithe agus comhthéacs buan a thaifeadadh agus a chuardach:

```bash
# Liosta de na cuimhní atá stóráilte
omi memory list

# Cuimhne nua a chruthú
omi memory create "Is fearr leis an úsáideoir freagraí teicniúla gonta le samplaí i Python" --category work

# Cuimhne shonrach a fháil de réir aitheantais
omi memory get <ID_CUIMHNE>
```

### Comhráite (Conversations)

Taifeadtaí fuaime agus athscríbhinní téacs ó ghléasanna Omi:

```bash
# Liosta de na 5 chomhrá is déanaí
omi conversation list --limit 5

# Comhrá a fháil mar aon leis an athscríbhinn iomlán
omi conversation get <ID_COMHRÁ> --include-transcript
```

### Míreanna gníomhaíochta (Action Items)

Tascanna agus cinntí a aithníodh go huathoibríoch le linn comhráite:

```bash
# Liosta de na gníomhartha oscailte
omi action-item list --open

# Marcáil gníomh mar chríochnaithe
omi action-item complete <ID_GNÍOMHAÍOCHTA>
```

### Spriocanna (Goals)

Monatóireacht a dhéanamh ar spriocanna fadtéarmacha agus ar dhul chun cinn:

```bash
# Liosta de na spriocanna gníomhacha
omi goal list

# Sprioc chainníochtúil a chruthú (tugtar an teideal mar argóint shuíomhach)
omi goal create "Iontógáil laethúil uisce" --type numeric --target 2500 --unit "ml"
```

---

## 4. Uathoibriú struchtúrtha agus aschur JSON (`--json`)

Tá `omi-cli` deartha go sonrach le haghaidh comhtháthú réidh i scripteanna agus i bpíblínte AI uathoibrithe. Soláthraíonn an bratach domhanda `--json` aschur glan JSON atá oiriúnach le próiseáil le huirlisí ar nós `jq`:

```bash
# Cuimhní a fháil i bhformáid JSON agus a scagadh le jq
omi --json memory list | jq '.[] | {id, content, category}'

# Teidil na 5 chomhrá is déanaí a bhaint as
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Liosta de na gníomhartha oscailte
omi --json action-item list --open | jq '.'
```

> **Riail ríthábhachtach chomhréire:**
> Is rogha dhomhanda é an bratach `--json` agus ní mór dó a bheith suite **roimh** an bhforordú i gcónaí:
> * Ceart: `omi --json memory list`
> * Mícheart: `omi memory list --json`

### Leathanú agus onnmhairiú sonraí

Agus tú ag obair le méideanna níos mó sonraí, bain úsáid as na paraiméadair `--limit` agus `--offset`:

```bash
# Sonraí a íoslódáil de réir leathanaigh
omi --json memory list --limit 25 --offset 0 > cuimhni-leathanach-1.json
omi --json memory list --limit 25 --offset 25 > cuimhni-leathanach-2.json
```

Cruthaíonn nó forscríobhann atreorú chuig comhad an comhad áitiúil. Seiceáil cód scoir an ordaithe i gcónaí sula ndéantar tuilleadh próiseála. Téann teachtaireachtaí earráide chuig an ngnáthshruth earráidí (`stderr`), mar sin ní ráthaíonn comhad folamh nach bhfuil sonraí ann. D'fhéadfadh sonraí rúnda a bheith i gcomhaid onnmhairithe — cosain iad de réir do rialacha slándála.

---

## 5. Cóid scoir (Exit Codes Contract)

Leanann `omi-cli` conradh beacht maidir le cóid scoir chun earráidí a láimhseáil go hiontaofa i scripteanna agus i gcórais CI/CD (de réir `omi_cli/errors.py`):

| Cód | Ainm | Brí agus cur síos |
| :---: | :--- | :--- |
| `0` | **Rath (`EXIT_OK`)** | Cuireadh an t-ordú i gcrích go rathúil gan aon earráid. |
| `1` | **Earráid úsáide / Bailíochtú feidhmchláir (`EXIT_USAGE`)** | Earráid bhailíochtaithe ar leibhéal feidhmchláir (`UsageError`, m.sh. úsáid chomhuaineach a bhaint as na roghanna frithpháirteacha `--browser` agus `--api-key`). |
| `2` | **Earráid fíordheimhnithe / Parsálaí (`EXIT_AUTH`)** | Dintiúir ar iarraidh, eochair atá as feidhm nó ceadanna neamhdhóthanacha. Cuireann earráidí comhréire agus luachanna neamhbhailí an pharsálaí Click/Typer (roghanna anaithnide, luachanna lasmuigh de raon le haghaidh `--limit`, luachanna neamhbhailí roghnóireachta nó argóintí ar iarraidh) cód 2 ar ais freisin. |
| `3` | **Earráid freastalaí nó líonra (`EXIT_SERVER`)** | Freagra HTTP 5xx ó fhreastalaí Omi nó cliseadh ar an nasc líonra. |
| `4` | **Teorainn ráta sáraithe (`EXIT_RATE_LIMITED`)** | Freagra HTTP 429 — an iomarca iarratas seolta laistigh d'achar gearr ama. |
| `5` | **Acmhainn gan aimsiú (`EXIT_NOT_FOUND`)** | Freagra HTTP 404 — níl an acmhainn a iarradh ann. |

---

## 6. Samplaí do thimpeallachtaí éagsúla teirminéil

### Bash / Zsh (Linux agus macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "D'éirigh le haistarraingt $(jq 'length' /tmp/memories.json) cuimhne."
else
    code=$?
    echo "Earráid le linn cuimhní a fháil (cód scoir: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Theip ar an ordú le cód scoir $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Sábháladh na sonraí go rathúil."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Tharla earráid le cód scoir %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Críochnaíodh an oibríocht go rathúil.
```

---

## 7. Bainistíocht próifílí agus timpeallacht thástála (Staging)

Ligeann an rogha `--profile` duit ilchumraíochtaí neamhspleácha a choinneáil (m.sh. pearsanta, oibre nó tástála). Maidir le timpeallachtaí tástála, is féidir bun-URL buan a shocrú don phróifíl:

```bash
# Bun-URL a shocrú go buan don phróifíl staging
omi --profile staging config set api_base https://api.staging.omi.me

# Logáil isteach sa phróifíl tástála (staging)
omi --profile staging auth login --api-key omi_dev_staging_eochair

# Orduithe a fhorghníomhú sa phróifíl staging (dírithe go buan ar an timpeallacht tástála)
omi --profile staging memory list

# Nó sárú sealadach a dhéanamh d'ordú ar leith:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Nóta tábhachtach faoi `--api-base`:** Ní ghníomhaíonn an bratach `--api-base` ach mar shárú sealadach don ordú sonrach sin agus ní shábháiltear go huathoibríoch é sa chumraíocht. Le haghaidh úsáide leanúnaí bain úsáid as `config set api_base <url>`.

---

## 8. Comhtháthú le API Deisce Áitiúil (Local Desktop API)

Má tá feidhmchlár Omi Desktop ag rith ar an meaisín céanna, is féidir leat cumarsáid dhíreach a dhéanamh leis an bhfreastalaí áitiúil gan sonraí a sheoladh chuig an néal. Sula ndéantar `omi local status` nó cuardaigh a fhorghníomhú, déan cinnte go bhfuil an seoladh agus an comhartha slándála socraithe agat:

```bash
# 1. Seoladh áitiúil (port réamhshocraithe 47778) agus comhartha a shocrú:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="bhur_dtóken_áitiúil"

# Nó sábháil go buan sa phróifíl:
# omi local configure --url http://127.0.0.1:47778 --token "bhur_dtóken_áitiúil"

# 2. Stádas na seirbhíse áitiúla a sheiceáil (éilíonn paraiméadair réamhshocraithe)
omi local status

# 3. Cuardach a dhéanamh i stair an scáileáin de réir ceiste agus feidhmchláir
omi local search-screen "cruinniú seachtainiúil" --days 1 --app "Slack"
```

---

## 9. Slándáil agus dea-chleachtais

1. **Suíomh an bhrataigh `--json`:** Cuir roimh an bhforordú i gcónaí é (`omi --json memory list`).
2. **Láimhseáil cóid scoir:** I scripteanna uathoibrithe seiceáil agus déileáil i gcónaí le cóid ó 1 go 5.
3. **Cosaint dintiúr:** Ná cuir eochracha API i stórtha cóid phoiblí riamh. I dtimpeallachtaí táirgthe agus CI/CD bain úsáid as an athróg `OMI_API_KEY`.
