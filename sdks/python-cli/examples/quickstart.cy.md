# Canllaw Cychwyn Cyflym omi-cli (Welsh Quickstart)

> Canllaw ymarferol ar gyfer rhyngweithio ag Omi yn uniongyrchol o'r derfynell — wedi'i gynllunio ar gyfer datblygwyr ac asiantau AI ymreolaethol.

`omi-cli` yw'r rhyngwyneb llinell orchymyn swyddogol ar gyfer API datblygwyr [Omi](https://omi.me). Mae'n darparu mynediad strwythuredig ac addas i asiantau at bedair prif adnodd Omi: **atgofion** (memories), **sgyrsiau** (conversations), **eitemau gweithredu** (action items), a **nodau** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dogfennaeth Swyddogol:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Cod Ffynhonnell:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Gosod

Er mwyn osgoi gwrthdaro rhwng pecynnau a chadw amgylchedd glân, argymhellir yn gryf defnyddio `pipx`:

```bash
# Dull a argymhellir: gosod mewn amgylchedd ynysig gyda pipx
pipx install omi-cli

# Neu drwy pip safonol (mewn amgylchedd rhithwir)
pip install omi-cli
```

> **Gwahaniaeth Pwysig: Enw'r Pecyn vs Enw'r Gorchymyn**
> * Enw'r pecyn gosod yw **`omi-cli`**.
> * Y gorchymyn gweithredu yn y derfynell yw **`omi`**.

Gwiriwch fod y gosodiad yn gweithio:

```bash
omi --version
```

---

## 2. Dilysu

Mae `omi-cli` yn cefnogi dau brif ddull dilysu: **OAuth trwy'r porwr** (ar gyfer defnyddwyr dynol) ac **Allweddi API Datblygwr** (ar gyfer sgriptiau ac asiantau AI).

### Dull A: OAuth trwy'r Porwr (Defnyddwyr)

Y dull rhagosodedig yw mewngofnodi trwy Google:

```bash
omi auth login
```

Neu mewngofnodwch gan ddefnyddio Apple ID:

```bash
omi auth login --provider apple
```

Mae hyn yn agor ffenestr borwr i gwblhau'r broses ddilysu ac yn cadw'r tocyn mynediad yn ddiogel yn `~/.omi/config.toml`.

### Dull B: Allwedd API Datblygwr (Awtomeiddio ac Asiantau)

Ar gyfer gweinyddion, llinellau gwaith CI/CD, neu asiantau ymreolaethol, defnyddiwch allwedd API datblygwr (`omi_dev_*`):

```bash
# Opsiwn 1: Gosod newidyn amgylchedd (dull a ffefrir ar gyfer cynwysyddion/gweinyddion)
export OMI_API_KEY="omi_dev_eich_allwedd_yma"

# Opsiwn 2: Dilysu a chadw yn y ffurfweddiad lleol
omi auth login --api-key "omi_dev_eich_allwedd_yma"
```

### Gwirio Statws Dilysu

Mae dau orchymyn i wirio'ch statws dilysu:

```bash
# Gwiriad all-lein lleol (yn darllen o'r ffeil ffurfweddu neu newidynnau amgylchedd)
omi auth status

# Galwad fyw i'r gweinydd (yn dilysu bod y tocyn/allwedd yn ddilys ac yn weithredol)
omi auth whoami
```

### Allgofnodi

I ddileu'r manylion dilysu o'r system leol:

```bash
omi auth logout
```

---

## 3. Rheoli Atgofion (Memories)

Atgofion yw'r ffeithiau a'r darnau gwybodaeth unigol y mae Omi yn eu cadw ar eich rhan.

```bash
# Rhestru atgofion diweddar (rhagosodiad yw 25)
omi memory list

# Rhestru gyda therfyn maint
omi memory list --limit 10

# Nodi safle dechrau (tudalennu)
omi memory list --limit 10 --offset 20

# Cael manylion atgof penodol yn ôl ei ID
omi memory get <memory-id>

# Creu atgof newydd â llaw
omi memory create "Hoff iaith raglennu'r tîm yw Python."
```

---

## 4. Sgyrsiau, Eitemau Gweithredu, a Nodau

### Sgyrsiau (Conversations)

```bash
# Rhestru sgyrsiau diweddar
omi conversation list

# Dangos manylion sgwrs benodol gan gynnwys y trawsgrifiad
omi conversation get <conversation-id>
```

### Eitemau Gweithredu (Action Items)

Tasgau neu gamau gweithredu a dynnwyd o sgyrsiau neu a grëwyd gennych chi:

```bash
# Rhestru eitemau gweithredu agored
omi action-item list

# Creu eitem weithredu newydd
omi action-item create "Adolygu'r canllawiau cyflym newydd cyn y cyfarfod."
```

### Nodau (Goals)

Amcanion tymor hir neu ganlyniadau rydych am eu cyflawni:

```bash
# Rhestru'r holl nodau gweithredol
omi goal list

# Creu nod newydd
omi goal create "Cwblhau integreiddio Omi CLI ar gyfer yr asiant cyn diwedd y chwarter."
```

---

## 5. Allbwn JSON ac Integreiddio Pibellau (jq)

I ddefnyddio `omi` o fewn sgriptiau awtomeiddio neu asiantau AI, defnyddiwch y faner fyd-eang `--json`.

> **Rheol Bwysig:** Rhaid gosod y faner `--json` **cyn** y ferf neu'r gorchymyn israddol:

```bash
# Yn Gywir:
omi --json memory list

# Yn Anghywir (bydd yn dychwelyd gwall Click):
omi memory list --json
```

### Enghreifftiau o ddefnyddio `jq`:

```bash
# Echdynnu dim ond yr IDs o'r atgofion
omi --json memory list | jq -r '.[].id'

# Echdynnu testun yr holl atgofion fel llinellau unigol
omi --json memory list | jq -r '.[].content'

# Cyfuno ID a thestun sgyrsiau mewn fformat cryno
omi --json conversation list | jq -r '.[] | "\(.id): \(.structured.title)"'

# Cyfrif nifer yr eitemau gweithredu agored
omi --json action-item list | jq 'length'
```

---

## 6. Codau Ymadael a Thrino Gwallau

Mae `omi-cli` yn dilyn contractau codau ymadael pendant yn unol ag `omi_cli/errors.py`:

| Cod | Enw Cysonyn | Math o Sefyllfa | Esboniad a Chamau Gweithredu |
| :---: | :--- | :--- | :--- |
| **`0`** | `EXIT_OK` | Llwyddiant | Cwblhawyd y gorchymyn yn ddiffael. |
| **`1`** | `EXIT_USAGE` | Camddefnydd Mewnol | Gwall dilysu mewnol o fewn `omi-cli` (e.e. pasio `--browser` ac `--api-key` gyda'i gilydd). *Sylwer:* Mae gwallau dosrannu Click safonol (megis baneri anhysbys) yn ymadael â chod **2**. |
| **`2`** | `EXIT_AUTH` | Dilysu / Mynediad | Tocyn ar goll, allwedd API annilys, neu sesiwn wedi dod i ben. Yn digwydd hefyd ar wallau dosrannu baneri Click. |
| **`3`** | `EXIT_SERVER` | Gwall Gweinydd / Rhwydwaith | Ymateb HTTP 5xx neu fethiant cysylltiad rhwydwaith. Nid oes sicrwydd a gwblhawyd gweithrediadau ysgrifennu ar y gweinydd. |
| **`4`** | `EXIT_RATE_LIMITED` | Cyfyngiad Cyfradd | Ymateb HTTP 429. Bydd y CLI yn ail-drio'n awtomatig gan barchu pennawd `Retry-After`. |
| **`5`** | `EXIT_NOT_FOUND` | Heb ei Ddarganfod | Ymateb HTTP 404. Nid yw'r ID a nodwyd yn bodoli neu fe'i dilëwyd. |

> **Adnewyddu Tocynnau:** Mae'r gorchymyn `omi auth refresh` ar gael ar gyfer sesiynau porwr (OAuth) yn unig. Ar gyfer allweddi API datblygwr bydd yn dychwelyd gwall (cod ymadael 1) — nid oes tocyn i'w adnewyddu.

---

## 7. Enghreifftiau Sgriptio Awtomeiddio

### Enghraifft Bash: Ysgrifennu Atgof a Thrino Codau Ymadael

```bash
#!/usr/bin/env bash
set -euo pipefail

TEXT="Cyfarfod tîm wedi'i drefnu ar gyfer dydd Llun am 10:00yb."

echo "Wrthi'n creu atgof newydd..."
if OUTPUT=$(omi --json memory create "$TEXT" 2>&1); then
  MEMORY_ID=$(echo "$OUTPUT" | jq -r '.id // empty')
  echo "Llwyddiant! ID yr atgof: $MEMORY_ID"
else
  STATUS=$?
  echo "Gwall wrth greu atgof (Cod ymadael: $STATUS)"
  case $STATUS in
    2) echo "Gwall dilysu: Gwirwch OMI_API_KEY neu rhedwch 'omi auth login'." ;;
    3) echo "Gwall gweinydd neu rwydwaith. Rhowch gynnig arall arni yn fuan." ;;
    4) echo "Cyfyngiad cyfradd wedi'i gyrraedd." ;;
    *) echo "Gwall arall: $OUTPUT" ;;
  esac
  exit $STATUS
fi
```

### Enghraifft PowerShell: Adalw Eitemau Gweithredu

```powershell
$response = omi --json action-item list | ConvertFrom-Json

foreach ($item in $response) {
    [PSCustomObject]@{
        Id        = $item.id
        Content   = $item.content
        CreatedAt = $item.created_at
    }
}
```

---

## 8. Nodweddion Uwch

### Cysylltu ag API Penbwrdd Lleol (Local Desktop API)

Os yw ap penbwrdd Omi yn rhedeg ar eich peiriant lleol, gall `omi-cli` gyfathrebu'n uniongyrchol ag ef ar borth `47778` heb orfod mynd trwy'r cwmwl:

```bash
# Ffurfweddu newidynnau amgylchedd ar gyfer yr API lleol
export OMI_LOCAL_API_URL="http://localhost:47778"
export OMI_LOCAL_TOKEN="eich_tocyn_lleol"

# Rhedwch orchmynion yn lleol
omi memory list
```

### Rheoli Proffiliau ac Amgylcheddau Profi (Staging)

Mae'r faner `--profile` yn caniatáu cadw ffurfweddiadau ar wahân (e.e. personol, gwaith, neu brofi). Caiff y ffurfweddiad ei gadw yn `~/.omi/config.toml`:

```bash
# Mewngofnodi i wahanol broffiliau
omi --profile personol auth login
omi --profile gwaith auth login

# Rhedeg gorchmynion dan broffil penodol
omi --profile gwaith memory list

# Cysylltu ag amgylchedd profi (staging)
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Diogelwch ac Arferion Gorau

* **Cadwch Allweddi'n Ddiogel:** Peidiwch byth ag ymrwymo allweddi `omi_dev_*` i ystorfeydd cod cyhoeddus (Git). Defnyddiwch newidynnau amgylchedd neu reolwr cyfrinachau bob amser.
* **Caniatadau Ffeiliau ar Unix:** Diogelwch gyfeiriadur ffurfweddu lleol Omi gyda chaniatadau cyfyngedig:
  ```bash
  chmod 700 ~/.omi
  ```
* **Glanhau Cymwysterau Dros Dro:** Ar beiriannau a rennir neu weinyddion dros dro, glanhewch y manylion dilysu ar ôl gorffen:
  ```bash
  unset OMI_API_KEY
  omi auth logout
  ```
