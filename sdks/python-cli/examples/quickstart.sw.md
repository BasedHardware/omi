# omi-cli — mwongozo wa haraka wa Kiswahili

> Mwongozo wa vitendo wa kufanya kazi na Omi kutoka kwenye terminali. Unafaa kwa binadamu na mawakala wa AI.

`omi-cli` ni mteja rasmi wa mstari wa amri kwa API ya wasanidi wa [Omi](https://omi.me).
Hutoa ufikiaji wa haraka na unaoweza kuandikwa kupitia rasilimali nne kuu za Omi:
kumbukumbu, mazungumzo, vitu vya hatua na malengo.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Nyaraka:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Msimbo wa chanzo:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Usakinishaji

Njia inayopendekezwa ni `pipx`: husakinisha chombo katika mazingira yaliyotengwa,
hivyo utegemezi wake hauingiliani na miradi yako.

```bash
# inayopendekezwa: sakinisha kwa pipx
pipx install omi-cli

# au kwa pip
pip install omi-cli
```

> **Muhimu: jina la kifurushi na jina la amri ni tofauti.**
> * Kifurushi kinachosakinishwa ni **`omi-cli`** (kifurushi tofauti `omi` ni mradi mwingine usiohusiana).
> * Baada ya usakinishaji unatekeleza amri **`omi`**.

Thibitisha kwamba kila kitu kinafanya kazi:

```bash
omi --version
omi --help
```

---

## 2. Uthibitishaji

`omi-cli` inasaidia njia mbili za kuingia.

| Njia | Inafaa kwa | Amri |
| :--- | :--- | :--- |
| **Ufunguo wa msanidi (`omi_dev_*`)** | CI/CD, hati, mawakala wa AI | `omi auth login --api-key ...` au kigeugeu cha mazingira |
| **Kuingia kwa kivinjari (Google/Apple)** | Kazi kwenye kompyuta yako mwenyewe | `omi auth login --browser` |

### Kuingia kwa kuingiliana

Endesha bila chaguo lolote na itakuuliza njia gani utumie.

```bash
omi auth login
# 1) Browser — ingia kwa Google au Apple (kwa binadamu)
# 2) API key — bandika ufunguo wa msanidi kutoka app.omi.me (kwa mawakala/CI)
```

Ukichagua ufunguo, uingizaji hufichwa ili ufunguo usibaki kwenye historia ya terminali.

### Kuingia moja kwa moja kwa kivinjari

```bash
omi auth login --browser
```

### Kuingia kwa ufunguo wa msanidi

Pata ufunguo kwenye [app.omi.me](https://app.omi.me) chini ya **Developer → API Keys**.

```bash
# hifadhi ufunguo kwenye usanidi
omi auth login --api-key omi_dev_...

# au pataishe kupitia mazingira — ni bora kwa CI/CD na kontena
export OMI_API_KEY=omi_dev_...
```

Kigeugeu cha mazingira `OMI_API_KEY` hutumika wakati hakuna ufunguo ulihifadhiwa
kwenye wasifu uliotumika, hivyo kwenye kontena hakuna kinachohitaji kuandikwa
kwenye diski. Ikiwa wasifu tayari una ufunguo, ufunguo huo hupata kipaumbele
juu ya kigeugeu cha mazingira.

### Thibitisha ufikiaji

Amri mbili zinajibu maswali tofauti na zisichanganywe:

* `omi auth status` — kile kilichohifadhiwa **hapa**: wasifu, ufunguo uliofichwa, tarehe ya kuisha.
  Hufanya kazi bila mtandao.
* `omi auth whoami` — ombi **kwa seva ya Omi**: huthibitisha ufunguo unakubalika kweli.
  Inahitaji mtandao.

```bash
omi auth status    # ukaguzi wa hapa, nje ya mtandao
omi auth whoami    # ukaguzi kwa seva
```

Sasisha tokeni inayokaribia kuisha bila kuingia tena — amri hii ni kwa vikao vya
kivinjari/OAuth **pekee**. Kwa wasifu uliothibitishwa kwa ufunguo wa API (`omi_dev_*`),
`omi auth refresh` hufeli kwa kosa la matumizi (kodi 1): hakuna tokeni ya kusasisha —
badilisha ufunguo kwenye programu ya wavuti ya Omi ukiitaji:

```bash
omi auth refresh
```

Ondoka:

```bash
omi auth logout
```

---

## 3. Amri za msingi

### Kumbukumbu (memories)

Ukweli na maarifa ambayo mfumo umekukumbuka kuhusu wewe.

```bash
# orodha ya kumbukumbu
omi memory list

# unda mpya
omi memory create "Mtumiaji anapendelea mandhari ya giza" --category lifestyle

# angalia moja maalum
omi memory get <MEMORY_ID>
```

### Mazungumzo (conversations)

Historia ya sauti na maandishi kutoka kwa kifaa au programu.

```bash
# mazungumzo 5 ya hivi karibuni
omi conversation list --limit 5

# mazungumzo kamili na unukuzi
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Vitu vya hatua (action items)

Kazi ambazo Omi imeziunganisho kutoka kwa mazungumzo.

```bash
# zilizo wazi tu
omi action-item list --open

# weka alama kama imekamilika
omi action-item complete <ACTION_ITEM_ID>
```

### Malengo (goals)

```bash
# orodha ya malengo
omi goal list

# rekodi thamani mpya ya maendeleo (inahitaji hoja ZOTE mbili: lengo na thamani)
omi goal progress <GOAL_ID> 25

# historia ya mabadiliko
omi goal history <GOAL_ID>
```

---

## Kuuliza kwa maneno ya kawaida (`ask`)

Amri tofauti ya ngazi ya juu: inachukua swali la lugha ya asili,
na jibu linajengwa kutoka kwa mazungumzo yako.

```bash
omi ask "nilifanya uamuzi gani kuhusu uhamisho"
omi --json ask "ni vitu gani vya hatua niliahidi kukamilisha wiki hii"
```

---

## 4. JSON na hati (`--json`)

`omi-cli` inaweza kutoa JSON inayosomeka na mashine. Chaguo la `--json` ni
**global** na lazima liwekwe **kabla** ya amri ndogo.

```bash
# kumbukumbu: toa id, maandishi na kategoria
omi --json memory list | jq '.[] | {id, content, category}'

# vichwa vya mazungumzo ya hivi karibuni
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# vitu vya hatua vilivyo wazi
omi --json action-item list --open | jq '.'
```

> **Kosa la kawaida.** `--json` linakuja kabla ya amri ndogo, si baadaye.
> * Sahihi: `omi --json memory list`
> * Makosa: `omi memory list --json`

Katika hali ya `--json`, ujumbe wa maendeleo na viburudisho kwa binadamu hupotea —
stdout ina hati moja halali ya JSON pekee. Makosa huenda kwa stderr
katika umbizo `{"error": "...", "detail": "..."}`.

---

## 5. Kodi za kutoka

Kodi za kutoka thabiti za kuamua katika hati.

| Kodi | Maana |
| :--- | :--- |
| `0` | Mafanikio |
| `1` | Kosa la matumizi (bendera mbaya, hoja inayohitajika imekosekana) |
| `2` | Uthibitishaji umeshindikana — kuingia kunahitajika |
| `3` | Kosa la seva/mtandao |
| `4` | Kiwango kimezidiwa — jaribu tena baadaye |
| `5` | Rasilimali haipatikani |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "kumbukumbu hiyo haipo" ;;
    *) echo "kosa $code" ;;
  esac
fi
```

---

## 6. Wasifu na usanidi

Ikiwa una akaunti au mazingira mengi, tenganiza kwa wasifu.
Mipangilio huhifadhiwa katika `~/.omi/config.toml`.

```bash
# ingia kwenye wasifu binafsi
omi --profile personal auth login

# ingia kwenye wasifu wa kazi
omi --profile work auth login

# endesha amri katika wasifu maalum
omi --profile work memory list
```

Wasifu unaotumika huamuliwa kwa mpangilio huu: chaguo la `--profile` (au `-p`)
huongoza juu ya yote; kisha kigeugeu cha mazingira `OMI_PROFILE`; kisha wasifu
uliotumika katika `~/.omi/config.toml`; na mwishoni wasifu `default` kama mbadala.

Angalia na badilisha usanidi yenyewe:

```bash
# kile kilichowekwa sasa
omi config show

# faili ya usanidi iko wapi
omi config path

# badilisha thamani
omi config set api_base https://api.omi.me
```

---

## 7. Hatua zifuatazo

* [`agent_quickstart.md`](./agent_quickstart.md) — jinsi ya kuunganisha `omi-cli` kwa wakala wa AI.
* [`shell_examples.sh`](./shell_examples.sh) — mifano ya shell iliyotayari.
* [Nyaraka za Omi](https://docs.omi.me/doc/developer/cli/introduction) — marejeo kamili ya amri.
