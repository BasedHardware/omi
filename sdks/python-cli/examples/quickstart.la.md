# omi-cli — dux celeris Latine scriptus

> Dux practicus ad Omi ex terminale agendum. Hominibus et agentibus intellegentiae artificialis pariter aptus.

`omi-cli` est cliens officialis lineae mandatorum pro API effectorum [Omi](https://omi.me).
Aditum celerem et scriptis accommodatum ad quattuor entitates primarias Omi praebet:
memoriae, colloquia, agenda et scopi.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentatio:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Fons codicis:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installatio

Modus commendatus est `pipx`: instrumentum in ambitu secluso installat,
ita ut dependentiae eius cum proiectis tuis non pugnent.

```bash
# commendatum: installatio per pipx
pipx install omi-cli

# vel per pip
pip install omi-cli
```

> **Grave: nomen fasciculi et nomen mandati differunt.**
> * Fasciculus qui installatur est **`omi-cli`** (fasciculus separatus `omi` est proiectum aliud nulla cognatione coniunctum).
> * Post installationem mandatum **`omi`** exsequeris.

Proba omnia recte fungi:

```bash
omi --version
omi --help
```

---

## 2. Auctenticatio

`omi-cli` duos modos introeundi sustinet.

| Modus | Aptissimus | Mandatum |
| :--- | :--- | :--- |
| **Clavis effectoris (`omi_dev_*`)** | CI/CD, scripta, agentes AI | `omi auth login --api-key ...` vel variabilis ambientis |
| **Introitus per navigatrum (Google/Apple)** | Labor in computatro proprio | `omi auth login --browser` |

### Introitus interactus

Sine signis mandatum ipsum rogat quem modum velis:

```bash
omi auth login
# 1) Browser — intra per Google vel Apple (commodum hominibus)
# 2) API key — clavem effectoris ex app.omi.me glutina (commodum agentibus et CI)
```

Si clavem eligis, ingressio celatur, ne clavis in historia terminalis relinquatur.

### Directe per navigatrum

```bash
omi auth login --browser
```

### Per clavem effectoris

Clavis petitur ex [app.omi.me](https://app.omi.me) sub **Developer → API Keys**.

```bash
# clavem in configuratione serva
omi auth login --api-key omi_dev_...

# vel eam per ambitum trade — melius pro CI/CD et vasis
export OMI_API_KEY=omi_dev_...
```

Variabilis ambientis `OMI_API_KEY` adhibetur cum profilum activum clavem servatam non habet,
itaque in vase nihil disco scribendum est. Si profilum iam clavem habet,
ea variabili ambientis antevertit.

### Introitum proba

Duo mandata quaestionibus diversis respondent neque confundenda sunt:

* `omi auth status` — quid **localiter** iacet: profilum, clavis velata, tempus exspirationis.
  Sine reti fungitur.
* `omi auth whoami` — interrogatio **ad servum Omi**: probat clavem revera
  accipi. Rete requiritur.

```bash
omi auth status    # probatio localis, sine reti
omi auth whoami    # probatio in servo
```

Sessionem OAuth exspiraturam renova sine novo introitu — hoc solum ad introitum per navigatrum (OAuth) pertinet. Pro clavibus `omi_dev_*` hoc mandatum nihil renovat; clavem in applicatione retiali sub `Developer → API Keys` commuta:

```bash
omi auth refresh
```

Exi:

```bash
omi auth logout
```

---

## 3. Mandata fundamentalia

### Memoriae (memories)

Facta et scientia quae systema de te memorat.

```bash
# index memoriarum
omi memory list

# novam crea
omi memory create "Utens thema fuscum praeoptat" --category lifestyle

# certam specta
omi memory get <MEMORY_ID>
```

### Colloquia (conversations)

Historia vocis et texti ex instrumento vel ex applicatione.

```bash
# quinque colloquia recentissima
omi conversation list --limit 5

# colloquium integrum cum transcriptione
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Agenda (action items)

Munera quae Omi ex colloquiis deduxit.

```bash
# aperta tantum
omi action-item list --open

# ut perfectum nota
omi action-item complete <ACTION_ITEM_ID>
```

### Scopi (goals)

```bash
# index scoporum
omi goal list

# novum valorem progressus registra (AMBO argumenta requiruntur: scopus et valor)
omi goal progress <GOAL_ID> 25

# historia mutationum
omi goal history <GOAL_ID>
```

---

## Quaere verbis tuis propriis (`ask`)

Mandatum separatum summi ordinis: quaestionem lingua naturali ponit,
responsioque ex colloquiis tuis propriis construitur.

```bash
omi ask "quid de migratione decreverim"
omi --json ask "quae munera hac septimana perficere promiserim"
```

---

## 4. JSON et scripta (`--json`)

`omi-cli` JSON machine-legibile edere potest. Signum `--json` **generale** est
ideoque **ante** submandatum ponitur.

```bash
# memoriae: id, textum et categoriam extrahe
omi --json memory list | jq '.[] | {id, content, category}'

# tituli colloquiorum recentissimorum
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# agenda aperta
omi --json action-item list --open | jq '.'
```

> **Error communis.** `--json` ante submandatum venit, non post.
> * Rectum: `omi --json memory list`
> * Pravum: `omi memory list --json`

In modo `--json` nihil nisi JSON ipsum ad stdout scribitur —
scripta hoc fidere possunt.

---

## 5. Codices exitus

Codices stabiles sunt, itaque logica scriptorum et CI ex iis ramificari potest.

| Codex | Significatio | Quando |
| :---: | :--- | :--- |
| `0` | Successus | Mandatum perfectum est |
| `1` | Error vocandi | validatio ipsius omi-cli (e.g. `--browser` et `--api-key` simul, optio invalida, stdin vacuum) |
| `2` | Error aditus vel argumentorum | non introisti, clavis invalida vel exspirata — necnon errores resolutoris (signum ignotum, argumentum deest) |
| `3` | Error servi | responsio 5xx, tempus excessum, connexio nulla |
| `4` | Nimiae petitiones | 429 Too Many Requests |
| `5` | Non inventum | 404, id non exstat |

Exemplum probationis in Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "clavis valet"
else
  code=$?
  [ "$code" -eq 2 ] && echo "iterum intra"
  [ "$code" -eq 3 ] && echo "servus non adest, postea iterum tempta"
fi
```

---

## 6. Variabiles ambientis

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_clavis_tua"

omi --json memory list --limit 10
```

Ut clavis in novis sessionibus legatur, lineam adde in `~/.bashrc` vel `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_clavis_tua"

# resolutio JSON per PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Pro configuratione perpetua:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_clavis_tua", "User")
```

---

## 7. Applicatio Omi Desktop localis

Si applicatio Omi Desktop currit, pars datorum directe,
nubem circumiens, attingi potest.

```bash
# indicem API localis indica
omi local configure --url http://127.0.0.1:47778 --token TESSERA_TUA

# proba eam respondere
omi --json local status

# quaestio in historia imaginum
omi --json local search-screen "pretia" --days 7 --app Safari

# imago per id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# SQL liberum in basin datorum localem
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Ordo laboris: primum `local status`, deinde `local tools` — ut instrumenta
praesentia et eorum parametros videas, et tum demum vocationes.

---

## 8. Profila

Si plures rationes vel ambitus habes, ea profilis seiunge.
Configurationes in `~/.omi/config.toml` servantur.

```bash
# intra in profilum personale
omi --profile personal auth login

# intra in profilum operis
omi --profile work auth login

# mandatum in certo profilo exsequere
omi --profile work memory list
```

Si profilum non indicas, CLI primum valorem variabilis ambientis `OMI_PROFILE` adhibet, deinde profilum activum ex file configurationis, deinde `default`. Ordo praestantiae: `--profile`, deinde `OMI_PROFILE`, deinde profilum activum in `~/.omi/config.toml`, deinde `default`.

Configurationem ipsam specta et muta:

```bash
# quid nunc configuratum est
omi config show

# ubi file configurationis iacet
omi config path

# valorem muta
omi config set api_base https://api.omi.me
```

---

## 9. Proximi gradus

* [`agent_quickstart.md`](./agent_quickstart.md) — quomodo `omi-cli` agenti AI iungatur.
* [`shell_examples.sh`](./shell_examples.sh) — exempla parata pro shell.
* [Documentatio Omi](https://docs.omi.me/doc/developer/cli/introduction) — plena mandatorum referentia.
