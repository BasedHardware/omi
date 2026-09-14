# omi-cli Flýtileiðarvísir (Icelandic Quickstart)

> Hagnýtur leiðarvísir um notkun Omi beint úr skipanalínunni — hannaður fyrir forritara og sjálfstæða gervigreindarsjálfvirka (AI) umboðsmenn.

`omi-cli` er opinbera skipanalínuviðmótið (CLI) fyrir forritaraviðmót [Omi](https://omi.me). Það veitir skipulagðan aðgang að 4 meginauðlindum Omi: minningum (*memories*), samtölum (*conversations*), aðgerðaliðum (*action items*) og markmiðum (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Opinber skjölun:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Frumkóði:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Uppsetning

Til að tryggja einangrað umhverfi og koma í veg fyrir árekstra við kerfispakka Python er eindregið mælt með því að nota `pipx`:

```bash
# Ráðlögð aðferð: einangruð uppsetning með pipx
pipx install omi-cli

# Annar valkostur: hefðbundin pip uppsetning (t.d. í sýndarumhverfi)
pip install omi-cli
```

> **Mikilvæg árétting: Pakkanafn samanborið við skipananafn**
> * Opinbert heiti pakkans á PyPI er **`omi-cli`** (pakkinn `omi` er annað og óviðkomandi verkefni).
> * Skipunin sem keyrð er í skelinni er einfaldlega: **`omi`**.

Staðfestið að uppsetningin hafi heppnast með því að kalla á útgáfunúmer og hjálparvalmynd:

```bash
omi --version
omi --help
```

---

## 2. Auðkenning (Authentication)

`omi-cli` styður tvær meginleiðir til auðkenningar:

| Aðferð | Hentar best fyrir | Dæmi um skipun |
| :--- | :--- | :--- |
| **API-lykill forritara (`omi_dev_*`)** | Sjálfvirkniskriftur, CI/CD, netþjóna, gervigreindarumboðsmenn | `omi auth login --api-key ...` eða `OMI_API_KEY` |
| **OAuth innskráning í vafra** | Staðbundna forritun á vinnutölvu | `omi auth login --browser` (Google) / `--provider apple` |

### Gagnvirk innskráning

Ef skipunin er keyrð án rofa birtist gagnvirk valmynd:

```bash
omi auth login
# 1) Browser — Innskráning með vafra (Google eða Apple)
# 2) API key — Líma inn forritaralykil frá app.omi.me
```

### Innskráning með vefvafra

```bash
# Hefðbundin innskráning með Google-reikningi
omi auth login --browser

# Annar valkostur: innskráning með Apple-auðkenni
omi auth login --browser --provider apple
```

### Innskráning með API-lykli forritara

Búið til API-lykil á stjórnborðinu á [app.omi.me](https://app.omi.me) undir **Developer → API Keys**:

```bash
# Vista lykilinn í virka staðbundna prófílnum
omi auth login --api-key omi_dev_thinn_lykill_her

# Eða stilla umhverfisbreytu (tilvalið fyrir Docker og CI/CD ferla):
export OMI_API_KEY="omi_dev_thinn_lykill_her"
```

### Staða auðkenningar

* `omi auth status`: Sýnir virkan prófíl og dulbúið auðkenni úr staðbundinni stillingu (virkar án nettengingar).
* `omi auth whoami`: Sendir fyrirspurn á netþjón Omi til að staðfesta gildi setunnar yfir netið.

```bash
omi auth status
omi auth whoami
```

### Útskráning (Logout)

Til að fjarlægja staðbundið vistuð auðkenni:

```bash
omi auth logout
# Ef umhverfisbreytan OMI_API_KEY var notuð skal fjarlægja hana úr setunni:
unset OMI_API_KEY
```

> **Öryggisathugasemd:** Stillingar eru geymdar í skránni `~/.omi/config.toml`. Í Unix-kerfum er ráðlagt að takmarka aðgangsheimildir: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Grunnaðgerðir

### Minningar (Memories)

Skráning og leit að varanlegum staðreyndum, athugunum og samhengi:

```bash
# Listi yfir vistaðar minningar
omi memory list

# Stofna nýja minningu
omi memory create "Notandi kýs hnitmiðuð tæknileg svör með Python-dæmum" --category work

# Sækja tiltekna minningu eftir auðkenni
omi memory get <AUÐKENNI_MINNINGAR>
```

### Samtöl (Conversations)

Hljóðupptökur og textaafrit frá Omi tækjum:

```bash
# Listi yfir 5 síðustu samtöl
omi conversation list --limit 5

# Sækja samtal ásamt öllu afritinu
omi conversation get <AUÐKENNI_SAMTALS> --include-transcript
```

### Aðgerðaliðir (Action Items)

Verkefni sem greind eru sjálfvirkt út úr samtölum:

```bash
# Listi yfir opna aðgerðaliði
omi action-item list --open

# Merkja aðgerðalið sem lokið
omi action-item complete <AUÐKENNI_LIÐAR>
```

### Markmið (Goals)

Eftirlit með langtímamarkmiðum og framvindu:

```bash
# Listi yfir virk markmið
omi goal list

# Stofna nýtt tölulegt markmið (heitið er staðsetningarfæribreyta)
omi goal create "Dagleg vatnsdrykkja" --type numeric --target 2500 --unit "ml"
```

---

## 4. Skipulögð sjálfvirkni og JSON úttak (`--json`)

`omi-cli` hentar einstaklega vel í skriftur og sjálfvirkniferla. Með altæka rofanum `--json` fæst hreint JSON-úttak til vinnslu með verkfærum eins og `jq`:

```bash
# Minningar sóttar á JSON-formi og síaðar með jq
omi --json memory list | jq '.[] | {id, content, category}'

# Titlar 5 síðustu samtala dregnir út
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Listi yfir opin verkefni
omi --json action-item list --open | jq '.'
```

> **Mikilvæg málskipunarregla:**
> Rofinn `--json` er **altækur valkostur** og verður alltaf að koma **á undan** undirskipuninni:
> * Rétt: `omi --json memory list`
> * Rangt: `omi memory list --json`

### Síðuskipting og útflutningur gagna

Þegar unnið er með mikið magn gagna skal nota stikana `--limit` og `--offset`:

```bash
# Gögn sótt í hlutum
omi --json memory list --limit 25 --offset 0 > minningar-sida-1.json
omi --json memory list --limit 25 --offset 25 > minningar-sida-2.json
```

Tilfærsla í skrá býr til eða yfirskrifar staðbundna skrá. Kannið alltaf lokakóða skipunarinnar áður en gögnin eru unnin. Villuboð berast um staðlaða villustrauminn (`stderr`), svo tóm skrá tryggir ekki að engin gögn séu til staðar. Útfluttar skrár geta innihaldið persónugreinanlegar upplýsingar — gætið öryggis þeirra samkvæmt reglum.

---

## 5. Lokakóðar (Exit Codes Contract)

`omi-cli` fylgir skýrum samningi um lokakóða til að tryggja áreiðanlega villumeðhöndlun í skriftum og CI/CD kerfum (samkvæmt `omi_cli/errors.py`):

| Kóði | Heiti | Merking og lýsing |
| :---: | :--- | :--- |
| `0` | **Árangur (`EXIT_OK`)** | Skipunin tókst fullkomlega án villna. |
| `1` | **Notkunarvilla / Forritsstaðfesting (`EXIT_USAGE`)** | Ógildar færibreytur eða staðfestingarvilla á forritsstigi (t.d. ef `--browser` og `--api-key` eru notuð samtímis). |
| `2` | **Auðkenningarvilla (`EXIT_AUTH`) / Þáttari** | Vantar auðkenni, lykill runninn út eða ófullnægjandi réttindi. Setningafræðivillur Click-þáttarans (óþekktir rofar/vantar færibreytur) skila einnig kóða 2. |
| `3` | **Þjóna- eða netvilla (`EXIT_SERVER`)** | HTTP 5xx villa frá netþjóni Omi eða rof á nettengingu. |
| `4` | **Fyrirspurnatakmörkun náð (`EXIT_RATE_LIMITED`)** | HTTP 429 svar — of margar fyrirspurnir á stuttum tíma. |
| `5` | **Úrræði fannst ekki (`EXIT_NOT_FOUND`)** | HTTP 404 svar — umbeðið eintak er ekki til. |

---

## 6. Dæmi fyrir mismunandi skeljaumhverfi

### Bash / Zsh (Linux og macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Tókst að sækja $(jq 'length' /tmp/memories.json) minningar."
else
    code=$?
    echo "Villa við að sækja minningar (lokakóði: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Skipunin mistókst með lokakóða $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Gögn vistuð giftusamlega."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Villa kom upp með lokakóða %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Aðgerð lauk með árangri.
```

---

## 7. Prófílstjórnun og prófunarumhverfi (Staging)

Rofinn `--profile` gerir kleift að viðhalda mörgum ólíkum stillingum hlið við hlið (t.d. persónulegum, vinnu eða prófunar). Fyrir prófunarumhverfi skal nota `--api-base`:

```bash
# Innskráning í prófunarprófíl (staging)
omi --profile staging --api-base https://api.staging.omi.me auth login --api-key omi_dev_staging_lykill

# Skipun keyrð undir prófunarprófíl
omi --profile staging memory list
```

---

## 8. Samþætting við staðbundið tölvuforrits-API (Local Desktop API)

Ef Omi forritið er í gangi á sömu tölvu er hægt að eiga í beinum samskiptum við staðbundna netþjóninn án þess að senda gögn í skýið. Áður en staðbundnar skipanir eru keyrðar skal stilla slóð og aðgangslykil:

```bash
# Stilla staðbundið vistfang (sjálfgefin gátt 47778) og aðgangslykil:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="thinn_stadbundni_lykill"

# Kanna stöðu staðbundnu þjónustunnar
omi local status

# Leita í skjásögu eftir fyrirspurn og forriti
omi local search-screen "verkefnafundur" --days 1 --app "Slack"
```

---

## 9. Öryggi og bestu starfsvenjur

1. **Staðsetning `--json` rofans:** Setjið hann alltaf á undan undirskipun (`omi --json memory list`).
2. **Meðhöndlun lokakóða:** Skoðið og bregðist við öllum lokakóðum frá 1 til 5 í sjálfvirkniskriftum.
3. **Öryggi API-lykla:** Setjið aldrei API-lykla í opinber kóðasöfn. Í raunkeyrslu og CI/CD skal nota umhverfisbreytuna `OMI_API_KEY`.
