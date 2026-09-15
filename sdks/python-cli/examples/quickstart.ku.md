# Rêbera destpêka bilez a omi-cli (Kurdish Quickstart)

> Rêbereke pratîk ji bo xebitandina Omi rasterast ji termînalê — ji bo pêşdebiran û ajanên AI yên xweser.

`omi-cli` navrûya rêzika-fermanê ya fermî ye ji bo API-ya pêşdebiran a [Omi](https://omi.me). Ew dihêle ku tu çar beşên bingehîn ên pergalê bi awayekî birêkûpêk û otomatîkkirî birêve bibî: bîranîn (memories), axaftin (conversations), xalên kirinê (action items) û armanc (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Belgeyên fermî:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Koda çavkanî:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Navên fermanan, vebijêrk û peyamên bernameyê bi îngilîzî dimînin; tenê nivîsa ravekirinê ya vê rêberê bi kurdî ye. README-ya îngilîzî çavkaniya sereke ye.

---

## 1. Sazkirin

Ji bo dûrketina ji nakokiyên girêdanê (dependency) û xebitandina CLI-yê di hawirdorek cuda de, `pipx` tê pêşniyarkirin:

```bash
# Pêşniyarkirî: sazkirina cuda bi pipx
pipx install omi-cli

# Alternatîf: bi pip di nav hawirdorek virtual a Python a çalak de
pip install omi-cli
```

> **Têbînî: Navê pakêtê li hember navê fermanê**
> * Navê pakêtê li ser PyPI **`omi-cli`** ye (navê `omi` yê pakêteke ne têkildar e).
> * Fermana ku tu di termînalê de dixebitînî tenê **`omi`** ye.

Piştrast bike ku sazkirin dixebite:

```bash
omi --version
omi --help
```

Heke termînal `omi` nebîne, kontrol bike ku hawirdora virtual çalak e an jî peldanka ku `pipx` pelên xebitandinê tê de datîne di `PATH`-a te de ye.

---

## 2. Piştrastkirina nasnameyê (Authentication)

`omi-cli` du rêbazên sereke yên piştrastkirinê piştgirî dike:

| Rêbaz | Bikaranîn | Mînak |
| :--- | :--- | :--- |
| **Kilîta API ya pêşdebir (`omi_dev_*`)** | Skrîpt, CI/CD, serverên bê ekran, ajanên AI | `omi auth login --api-key ...` an `OMI_API_KEY` |
| **OAuth-a gerokê (Google/Apple)** | Stasyonên xebatê yên herêmî û pêşdebir | `omi auth login --browser` (Google) / `--provider apple` |

### Têketina înteraktîf
Bê ti ala bixebitîne da ku rêbazê bi awayê înteraktîf hilbijêrî:

```bash
omi auth login
# 1) Browser — gerokê ji bo têketina Google vedike (ji bo Apple `--provider apple` bi kar bîne)
# 2) API key — kilîta API ji app.omi.me bizeliqîne (têketin veşartî ye)
```

### Têketina rasterast bi gerokê
```bash
# Standard: têketina Google
omi auth login --browser

# Alternatîf: têketina Apple
omi auth login --browser --provider apple
```

### Bikaranîna kilîta API ya pêşdebir
Kilîtekê di [app.omi.me](https://app.omi.me) de di bin **Developer → API Keys** de çêke:

```bash
# Kilîtê di profîla herêmî ya çalak de tomar bike
omi auth login --api-key omi_dev_tokena_te_ya_rast

# An jî wekî guhêrbara hawirdorê diyar bike (ji bo konteyner û CI/CD baştirîn)
export OMI_API_KEY="omi_dev_tokena_te_ya_rast"
```

> `OMI_API_KEY` tenê wê demê tê bikaranîn ku profîla çalak kilîteke tomarkirî tune be. Heke tu berê bi `omi auth login` têketibî û dixwazî guhêrbara hawirdorê bandor bike, pêşî `omi auth logout` bixebitîne.

### Kontrolkirina rewşa piştrastkirinê
* `omi auth status`: profîla çalak û nasnameya veşartî nîşan dide (herêmî/offline dixebite; dîroka bidawîbûnê tenê ji bo tokenên OAuth derbasdar e).
* `omi auth whoami`: daxwazekê ji servera Omi re dişîne da ku derbasdariyê piştrast bike (tor pêwîst e).

```bash
omi auth status
omi auth whoami
```

Nûkirina tokena OAuth bê têketina dîsa:

```bash
omi auth refresh
```

> `omi auth refresh` tenê ji bo profîlên ku bi gerokê (OAuth) têketine dixebite. Ji bo profîlên li ser kilîta API tiştek ji bo nûkirinê tune ye û ferman bi peyama «Nothing to refresh» û koda derketinê `1` diqede.

Derketin:
```bash
omi auth logout
# Heke OMI_API_KEY di hawirdorê de hatibe diyarkirin, wê jî rake (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Fermanên bingehîn

### Bîranîn (Memories)
Rastiyên birêkûpêk û çavdêriyên çarçoveyî yên ku Omi tomar kirine:

```bash
# Bîranînan rêz bike
omi memory list

# Bîranîneke nû bi kategoriyê çêke
omi memory create "Bersivên teknîkî yên kurt bi mînakên Python tercîh dikim" --category work

# Bîranîneke taybet bi ID bistîne
omi memory get <MEMORY_ID>
```

### Axaftin (Conversations)
Tomarkirinên dengî, transkrîpt û diyalogên ku amûrên Omi tomar kirine:

```bash
# 5 axaftinên dawî rêz bike
omi conversation list --limit 5

# Hûrguliyên axaftinekê bi transkrîpta tevahî bistîne
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Xalên kirinê (Action Items)
Karên ku bi awayê otomatîk ji axaftinan hatine derxistin:

```bash
# Xalên kirinê yên vekirî rêz bike
omi action-item list --open

# Xaleke kirinê wekî temambûyî nîşan bike
omi action-item complete <ACTION_ITEM_ID>
```

### Armanc (Goals)
Nîşanderên pêşketinê û armancên demdirêj:

```bash
# Armancên çalak rêz bike
omi goal list

# Armanceke hejmarî ya nû çêke
omi goal create "Rojane 2 lître av vexwe" --type numeric --target 2 --unit liters

# Nirxa niha ya armancekê nû bike (ID û nirxa nû)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. Otomasyona birêkûpêk û derana JSON (`--json`)

`omi-cli` ji bo otomasyonê di pipeline û zincîreyên amûran de hatiye çêkirin. Alaya gerdûnî `--json` JSON-a paqij û makîne-xwendinbar vedigerîne:

```bash
# Bîranînan wekî JSON rêz bike û bi jq parzûn bike
omi --json memory list | jq '.[] | {id, content, category}'

# Sernavên axaftinên dawî bistîne
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Hemû xalên kirinê yên vekirî wekî JSON-a xav bibîne
omi --json action-item list --open | jq '.'
```

> **Rêgeza girîng a hevoksaziyê:**
> `--json` **vebijêrkeke gerdûnî** ye û divê **berî** jêrfermanê were danîn:
> * Rast: `omi --json memory list`
> * Şaş: `omi memory list --json`

### Rûpelkirin (Pagination)
Fermanên `list` piştgiriya `--limit` û `--offset` dikin:

```bash
omi --json memory list --limit 50 --offset 50
```

### Derxistina bo pelê
Ji bo ku rengên ANSI an tîpên kontrolê pelê qirêj nekin, stdout-ê rasterast di şelê de beralî bike:

```bash
# Bîranînan rasterast bo pelekî JSON-a paqij derxe
omi --json memory list > memories.json
```

---

## 5. Kodên derketinê (Exit Codes Contract)

Ji bo birêvebirina xeletiyan a pêbawer di CI/CD û skrîptan de, `omi-cli` peymaneke hişk a kodên derketinê dişopîne (binêre `omi_cli/errors.py`):

| Kod | Nav | Ravekirin û mînak |
| :---: | :--- | :--- |
| `0` | **Serkeftin (`EXIT_OK`)** | Kirar bê xeletî temam bû. |
| `1` | **Xeletiya bikaranînê (`EXIT_USAGE`)** | Xeletiyên rastandinê yên omi-cli bi xwe: `--browser` û `--api-key` yên ku bi hev re nayên bikaranîn, hilbijartineke nederbasdar di têketina înteraktîf de, têketina vala ji stdin, an `omi auth refresh` li ser profîleke kilîta API. |
| `2` | **Xeletiya piştrastkirinê (`EXIT_AUTH`)** | Nasnameya kêm an nederbasdar, an danişîna bidawîbûyî. Têbînî: alayeke nenas an argumaneke kêm jî ji aliyê Click bi xwe ve tê redkirin û bi koda `2` derdikeve. |
| `3` | **Xeletiya serverê (`EXIT_SERVER`)** | HTTP 5xx ji servera Omi an qutbûna torê. |
| `4` | **Sînorkirina rêjeyê (`EXIT_RATE_LIMITED`)** | HTTP 429 — di demeke kurt de pir daxwaz. |
| `5` | **Nehat dîtin (`EXIT_NOT_FOUND`)** | HTTP 404 — çavkaniya xwestî (bîranîn, axaftin, xala kirinê) tune ye. |

---

## 6. Mînak ji bo şelên cuda

### Bash / Zsh (Linux / macOS)
```bash
# Kilîta API ji bo vê danişînê diyar bike
export OMI_API_KEY="omi_dev_tokena_te_ya_rast"

# Fermanê bixebitîne û koda derketinê kontrol bike
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Xeletî di stendina bîranînan ji Omi de." >&2
fi
```

### PowerShell (Windows)
```powershell
# Guhêrbara hawirdorê di PowerShell de diyar bike
$env:OMI_API_KEY = "omi_dev_tokena_te_ya_rast"

# Derana JSON rasterast veguherîne objeya PowerShell
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Kontrola xeletiyê bi $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Fermana Omi bi koda derketinê $LASTEXITCODE bi ser neket."
}
```

---

## 7. Entegrasyona API-ya Desktop a herêmî (Omi Desktop)

Dema Omi Desktop li ser makîneya te dixebite (porta standard 47778), tu dikarî bê derbasbûna ji ewrê rasterast bi çarçoveya herêmî re bixebitî:

```bash
# Girêdana API-ya herêmî mîheng bike (ji bo parastina tokenê guhêrbarên hawirdorê bi kar bîne)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Tokena Desktop binivîse: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Rewşa girêdana herêmî piştrast bike
omi --json local status

# Di dîroka ekrana herêmî de bigere
omi --json local search-screen "Rapora çaryekê" --days 7 --app Safari
```

Li şûna guhêrbarên hawirdorê tu dikarî mîhengan li ser profîlê tomar bikî: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Birêvebirina çend profîlan (Profiles)

`--profile` bi kar bîne da ku bi hêsanî di navbera hesabê kesane, profîla kar an hawirdora ceribandinê de biguherî. Mîheng di `~/.omi/config.toml` de tên tomarkirin. Rêza pêşîniyê: alaya `--profile`, paşê guhêrbara hawirdorê `OMI_PROFILE`, û di dawiyê de profîla `default`.

```bash
# Profîla kesane çêke û têkeve
omi --profile personal auth login

# Profîla kar çêke û têkeve
omi --profile work auth login

# Fermanê bi profîleke taybet bixebitîne
omi --profile work memory list

# Profîlê bi guhêrbara hawirdorê hilbijêre
export OMI_PROFILE=work
omi memory list

# Xala dawî ya taybet ji bo ceribandinê bi kar bîne
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Rêbernameyên ewlehiyê û pratîkên baştirîn

* **Kilîtan di kodê de nenivîse:** Kilîtên API (`omi_dev_*`) ti carî li depoya Git commit neke. Pelên `.env` yên di `.gitignore` de an rêveberên nehêniyan ên ewle bi kar bîne.
* **Dîroka şelê biparêze:** Li ser serverên hevpar kilîtan wekî argumanên rêzika-fermanê yên eşkere neşîne; têketina înteraktîf an `OMI_API_KEY` bi kar bîne.
* **Destûrên peldankê teng bike:** Li ser Unix/macOS piştrast bike ku peldanka mîhengê destûrên sînordar hene:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Paqijkirina danişînê:** Dema hawirdorên demkî radikî, jibîr neke ku guhêrbara hawirdorê rakî:
  ```bash
  unset OMI_API_KEY
  ```
