# omi-cli — ātrais sākums latviešu valodā

> Praktisks ceļvedis darbam ar Omi no termināļa. Piemērots gan cilvēkam, gan AI aģentam.

`omi-cli` ir oficiālā komandrindas saskarne [Omi](https://omi.me) izstrādātāju API.
Tā nodrošina ātru un skriptojamu piekļuvi četrām galvenajām Omi entītijām:
atmiņām (memories), sarunām (conversations), uzdevumiem (action items) un mērķiem (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentācija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Pirmkods:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalēšana

Ieteicamais veids ir `pipx`: tas instalē rīku izolētā vidē,
tāpēc tā atkarības nesadursies ar jūsu projektiem.

```bash
# ieteicams: instalēšana ar pipx
pipx install omi-cli

# vai ar pip
pip install omi-cli
```

> **Svarīgi: pakotnes nosaukums un komandas nosaukums atšķiras.**
> * Tiek instalēta pakotne **`omi-cli`** (atsevišķā pakotne `omi` ir cits, nesaistīts projekts).
> * Pēc instalēšanas tiek palaista komanda **`omi`**.

Pārbaudiet, vai instalēšana izdevās:

```bash
omi --version
omi --help
```

---

## 2. Pieslēgšanās

`omi-cli` atbalsta divus pieslēgšanās veidus.

| Veids | Kad piemērots | Komanda |
| :--- | :--- | :--- |
| **Izstrādātāja atslēga (`omi_dev_*`)** | CI/CD, skripti, AI aģenti | `omi auth login --api-key ...` vai vides mainīgais |
| **Pieslēgšanās caur pārlūku (Google/Apple)** | Darbs pie sava datora | `omi auth login --browser` |

### Interaktīvā pieslēgšanās

Bez karodziņiem komanda pati pajautās, kā vēlaties pieslēgties:

```bash
omi auth login
# 1) Browser — pieslēgšanās caur Google vai Apple (ērti cilvēkam)
# 2) API key — ielīmēt izstrādātāja atslēgu no app.omi.me (ērti aģentiem un CI)
```

Izvēloties atslēgu, ievade tiek maskēta, tāpēc atslēga nepaliek termināļa vēsturē.

### Tūlīt caur pārlūku

```bash
omi auth login --browser
```

### Ar izstrādātāja atslēgu

Atslēgu iegūstat vietnē [app.omi.me](https://app.omi.me) sadaļā **Developer → API Keys**.

```bash
# saglabāt atslēgu konfigurācijā
omi auth login --api-key omi_dev_...

# vai nodot caur vidi — labāk piemērots CI/CD un konteineriem
export OMI_API_KEY=omi_dev_...
```

Mainīgais `OMI_API_KEY` tiek izmantots, kad aktīvajam profilam nav saglabātas atslēgas,
tāpēc konteinerā nekas nav jāraksta diskā. Ja atslēga profilā jau ir
saglabāta, tai ir prioritāte pār vides mainīgo.

### Pieslēgšanās pārbaude

Divas komandas atbild uz dažādiem jautājumiem, un tās nevajadzētu jaukt:

* `omi auth status` — kas ir saglabāts **lokāli**: profils, maskētā atslēga, derīgums.
  Strādā bez tīkla.
* `omi auth whoami` — vaicājums **uz Omi serveri**: pārbauda, vai serveris atslēgu
  patiešām pieņem. Nepieciešams tīkls.

```bash
omi auth status    # lokālā pārbaude, bezsaistē
omi auth whoami    # pārbaude serverī
```

Atjaunināt atslēgu, kurai tuvojas derīguma termiņš, bez atkārtotas pieslēgšanās:

```bash
omi auth refresh
```

Atteikšanās:

```bash
omi auth logout
```

---

## 3. Pamata komandas

### Atmiņas (memories)

Fakti un zināšanas, ko sistēma par jums ir iegaumējusi.

```bash
# atmiņu saraksts
omi memory list

# izveidot jaunu
omi memory create "Lietotājs izvēlas tumšo tēmu" --category lifestyle

# apskatīt konkrētu
omi memory get <MEMORY_ID>
```

### Sarunas (conversations)

Runas un teksta vēsture no ierīces vai no lietotnes.

```bash
# pēdējās 5 sarunas
omi conversation list --limit 5

# visa saruna kopā ar transkripciju
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Uzdevumi (action items)

Darbi, kurus Omi izdalījis no sarunām.

```bash
# tikai nepabeigtos
omi action-item list --open

# atzīmēt kā pabeigtu
omi action-item complete <ACTION_ITEM_ID>
```

### Mērķi (goals)

```bash
# mērķu saraksts
omi goal list

# ierakstīt jaunu progresa vērtību (vajadzīgi ABI argumenti: mērķis un vērtība)
omi goal progress <GOAL_ID> 25

# izmaiņu vēsture
omi goal history <GOAL_ID>
```

---

## Jautājums saviem vārdiem (`ask`)

Atsevišķa augstākā līmeņa komanda: uzdod jautājumu dabiskā valodā,
atbilde tiek veidota no jūsu pašu sarunām.

```bash
omi ask "ko es nolēmu par pārcelšanos"
omi --json ask "kādus uzdevumus es apsolīju pabeigt šonedēļ"
```

---

## 4. JSON un skripti (`--json`)

`omi-cli` prot atdot mašīnlasāmu JSON. Karodziņš `--json` ir **globāls**,
tāpēc tas jāliek **pirms** apakškomandas.

```bash
# atmiņas: izvilkt id, tekstu un kategoriju
omi --json memory list | jq '.[] | {id, content, category}'

# pēdējo sarunu virsraksti
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# nepabeigtie uzdevumi
omi --json action-item list --open | jq '.'
```

> **Bieža kļūda.** `--json` iet pirms apakškomandas, nevis pēc tās.
> * Pareizi: `omi --json memory list`
> * Nepareizi: `omi memory list --json`

Režīmā `--json` uz standarta izvadi nenonāk nekas, izņemot pašu JSON, —
uz to skriptos var paļauties.

---

## 5. Izejas kodi

Kodi ir stabili, tāpēc pēc tiem var zarot loģiku skriptos un CI.

| Kods | Nozīme | Kad rodas |
| :---: | :--- | :--- |
| `0` | Veiksme | Komanda pabeigta |
| `1` | Izsaukšanas kļūda | Nederīgs karodziņš, trūkst argumenta |
| `2` | Piekļuves kļūda | Nav pieslēgts, atslēga nederīga vai beigusies |
| `3` | Servera kļūda | Atbilde 5xx, timeout, nav savienojuma |
| `4` | Pārāk daudz pieprasījumu | 429 Too Many Requests |
| `5` | Nav atrasts | 404, norādītais identifikators neeksistē |

Pārbaudes piemērs Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "atslēga strādā"
else
  code=$?
  [ "$code" -eq 2 ] && echo "jāpieslēdzas no jauna"
  [ "$code" -eq 3 ] && echo "serveris nav pieejams, mēģiniet vēlāk"
fi
```

---

## 6. Vides mainīgie

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_jusu_atslega"

omi --json memory list --limit 10
```

Lai atslēga tiktu ielādēta jaunās sesijās, pievienojiet rindu failam `~/.bashrc` vai `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_jusu_atslega"

# JSON apstrāde ar PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Pastāvīga iestatīšana:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_jusu_atslega", "User")
```

---

## 7. Lokālā Omi Desktop lietotne

Ja darbojas Omi darbvirsmas lietotne, daļa datu ir pieejama tieši,
apejot mākoni.

```bash
# norādīt lokālā API adresi
omi local configure --url http://127.0.0.1:47778 --token JUSU_TOKENS

# pārbaudīt, vai tā atbild
omi --json local status

# meklēt ekrāna vēsturē
omi --json local search-screen "tarifi" --days 7 --app Safari

# ekrānuzņēmums pēc identifikatora
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# patvaļīgs SQL vaicājums lokālajā datubāzē
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Darba secība: vispirms `local status`, tad `local tools` — lai uzzinātu
pieejamos rīkus un to parametrus — un tikai pēc tam izsaukumi.

---

## 8. Profili

Ja kontu vai vidi ir vairākas, atdaliet tās ar profiliem.
Iestatījumi tiek glabāti failā `~/.omi/config.toml`.

```bash
# pieslēgties personīgajam profilam
omi --profile personal auth login

# pieslēgties darba profilam
omi --profile work auth login

# izpildīt komandu konkrētā profilā
omi --profile work memory list
```

Aplūkot un mainīt pašu konfigurāciju:

```bash
# kas šobrīd ir iestatīts
omi config show

# kur atrodas konfigurācijas fails
omi config path

# mainīt vērtību
omi config set api_base https://api.omi.me
```

---

## 9. Kas tālāk

* [`agent_quickstart.md`](./agent_quickstart.md) — kā pieslēgt `omi-cli` AI aģentam.
* [`shell_examples.sh`](./shell_examples.sh) — gatavi čaulas piemēri.
* [Omi dokumentācija](https://docs.omi.me/doc/developer/cli/introduction) — pilna komandu rokasgrāmata.
