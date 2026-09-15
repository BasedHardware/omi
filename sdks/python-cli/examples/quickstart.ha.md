# omi-cli — Jagorar Fara Sauri a Hausa (Hausa Quickstart)

> Jagorar amfani mai amfani game da yin aiki da Omi daga m (terminal). An yi ta ne don masu shirya software (developers) da wakilan AI (AI agents).

`omi-cli` ita ce kayan aiki na hanyar umarni (CLI) na hukuma don API na masu shirya software na [Omi](https://omi.me). Tana ba ka damar sarrafawa da sarrawa ba tare da hannu ba bangarori hudu masu muhimmanci: abubuwan tunawa (memories), hira (conversations), ayyukan da za a yi (action items), da burin (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Takardun hukuma:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Koden tushe:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Shigarwa (Installation)

Hanyar da aka fi ba da shawara ita ce amfani da `pipx`: tana sanya kayan aiki a cikin yanayi na daban (isolated environment) don kada ta rikice sauran ayyukan gare ka:

```bash
# Hanyar da aka ba da shawara: shigarwa ta hanyar pipx
pipx install omi-cli

# Ko kuma da kwararrun pip
pip install omi-cli
```

> **Ka tuna: Sunan kunshin da sunan umarni ba su daidai ba.**
> * Sunan kunshin a kan PyPI shine **`omi-cli`** (sunan `omi` da kansa wani aiki ne na daban wanda ba shi da alaka da wannan).
> * Bayan an shigar da shi, abin da ka ke kira a m shine **`omi`**.

Tabbatar cewa komai yana aiki da kyau ta hanyar duba sigar da menu na taimako:

```bash
omi --version
omi --help
```

---

## 2. tabbatacciyar tantancewa (Authentication)

`omi-cli` tana goyan bayan hanyoyin shiga biyu masu muhimmanci:

| Hanya | Lokacin da ta fi dacewa | Umarni |
| :--- | :--- | :--- |
| **Maɓallin API na mai shirya (`omi_dev_*`)** | Ayyukan sarrawa ta atomatik, CI/CD, sabar mara hoto, wakilan AI | `omi auth login --api-key ...` ko canjin yanayi (environment variable) |
| **Browser OAuth (Google/Apple)** | Kwamfuta ta sirri da masu shirya software na gida | `omi auth login --browser` (Google) / `--provider apple` |

### Shigar da ke tambaya (Interactive login)

Idan ka gudanar da umarnin ba tare da zabi ba, zai nemi ka zaba hanya:

```bash
omi auth login
# 1) Browser — shiga ta Google (ko akautin Apple: --provider apple)
# 2) API key — shigar da maɓallin API da ka kirkira a app.omi.me
```

### Shigar da kai tsaye ta browser

```bash
# Fara da Google
omi auth login --browser

# Ko kuma da Apple
omi auth login --browser --provider apple
```

### Shiga da maɓallin API na mai shirya

Kirkira maɓallin ka a cikin panel ɗin [app.omi.me](https://app.omi.me) a ƙarƙashin **Developer → API Keys**:

```bash
# Ajiye maɓallin a cikin bayanan martaba na gida ta umarni
omi auth login --api-key omi_dev_...

# Ko kuma saka shi a matsayin canjin yanayi (mafi kyau ga kwantena da CI/CD)
# Bayani: Idan an riga an saka maɓallin a cikin bayanan martaba mai aiki, gudu `omi auth logout` farko.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### Duba halin tabbatacciyar tantancewa

Wadannan umarni biyu suna ba da bayani daban-daban, kada a hada su:

* `omi auth status` — yana nuna abin da ke **cikin kwamfutarka (ba tare da intanet ba)**: bayanan martaba mai aiki, maɓallin da aka boye (masked), da lokacin da za ta kare. Ba ta bukatar intanet ba.
* `omi auth whoami` — yana magana da **sabar Omi**: yana tabbatar da cewa maɓallin yana aiki da gaske. Yana bukatar intanet.

```bash
omi auth status
omi auth whoami
```

Don fita:

```bash
omi auth logout
# Idan OMI_API_KEY tana cikin yanayi, cire ta daga can ma (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Umarnin Ƙarshe (Basic Commands)

### Abubuwan tunawa (Memories)

Bayanai masu gajeru da Omi ta rubuta kuma ta adana:

```bash
# Jerin abubuwan tunawa da aka adana
omi memory list

# Kirkirar sabon abu na tunawa
omi memory create "Ina son amsoshi na fasaha masu takaice da misalan Python" --category work

# Kawo cikakkun bayanai na tunawa ta musamman
omi memory get <MEMORY_ID>
```

### Hira (Conversations)

Rikodin magana da tattaunawa daga na'urorin Omi:

```bash
# Jerin sababbin hira 5
omi conversation list --limit 5

# Kawo cikakkun bayanai da cikakken rubutun hira
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Ayyukan da za a yi (Action Items)

Ayyukan da aka ciro ta atomatik daga hira:

```bash
# Jerin ayyukan da aka bude
omi action-item list --open

# Kammala aiki
omi action-item complete <ACTION_ITEM_ID>
```

### Burin (Goals)

Ci gaba da burin dogon lokaci:

```bash
# Jerin burin masu aiki
omi goal list

# Kirkirar sabon burin lamba
omi goal create "Sha ruwa 2L kowace rana" --type numeric --target 2 --unit liters
```

---

## 4. Sarrafawa da fitarwa JSON (`--json`)

`omi-cli` tana da goyan baya mai kyau don hanyoyin sarrawa ta atomatik (automation pipelines). Idan ka sanya alamar `--json` gaba daya, fitarwa zai fito a cikin tsari na JSON na gaskiya:

```bash
# Jerin abubuwan tunawa a matsayin JSON, ka bar jq ta fitar da filaye
omi --json memory list | jq '.[] | {id, content, category}'

# Kawo take na hirarrakin sababbi
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Nuna ayyukan da ke bukin a matsayin JSON
omi --json action-item list --open | jq '.'
```

> **Dokar da ta fi muhimmanci:** Alamar `--json` **zabi ne na gaba daya** kuma dole ta bi kafin umarnin karami:
> * Daidai: `omi --json memory list`
> * Ba daidai ba: `omi memory list --json`

---

## 5. Ka'idojin Fita (Exit Codes)

Don duba kuskure mai amana a cikin rubutun shell da ayyukan CI/CD:

| Ka'idar Fita | Yana nufin | Bayani |
| :---: | :--- | :--- |
| `0` | **Nasara** | Aikin ya gamu ba tare da kuskure ba. |
| `1` | **Kuskuren amfani (Kuskuren tantancewa)** | Darajar ba daidai ba ko kuskuren tantancewa; kuskuren tsarin Click ya dawo da lambar `2`. |
| `2` | **Kuskuren tantancewa / tsarin CLI** | Ba a ba da izini ba, maɓallin ya kare, ko zabi na Click ba a sani ba. |
| `3` | **Kuskuren sabar / hanyar sadarwa** | Amsar HTTP 5xx, lokaci ya wuce (timeout), ko ba za a iya isa sabar ba. |
| `4` | **An hana girman (Rate Limited)** | HTTP 429 — buƙatar ta wuce iyakar lokaci. |
| `5` | **Ba a samu ba (Not Found)** | HTTP 404 — abin da ake nema ba ya wanzu. |

---

## 6. Misalan Yanayin Shell (Shell Examples)

### Bash / Zsh (Linux / macOS)

```bash
# Saka maɓallin API don wannan zaman
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Gudanar da umarnin kuma duba ka'idar fita
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Ba za a iya tambayar abubuwan tunawa ba." >&2
fi
```

### PowerShell (Windows)

```powershell
# Saka maɓallin API a matsayin canjin yanayi
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# Canza fitarwar JSON zuwa abu mai amfani
$memories = omi --json memory list | ConvertFrom-Json

# Yi amfani da $LASTEXITCODE don duba kuskure
if ($LASTEXITCODE -ne 0) {
    Write-Error "Umarnin omi ya kasa da lambar $LASTEXITCODE."
}
```

---

## 7. Haɗin API na Gida (Local Desktop API)

Lokacin da app ɗin Omi Desktop ke aiki a kwamfutarka, zaka iya yin tambayoyin gida ba tare da zuwa gajimare (cloud) ba:

```bash
# Saita tashar gida (yi amfani da canjin yanayi don kare maɓallin)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Duba halin haɗin gida
omi --json local status

# Bincika a cikin tarihin nuni na baya-bayan nan
omi --json local search-screen "Rahoton wata" --days 7 --app Safari
```

---

## 8. Sarrafa Bayanan Martaba da Dama (Profiles)

Canza tsakanin asusu na sirri da na aiki, ko yanayin gwaji, ta hanyar `--profile`. Saituna suna cikin `~/.omi/config.toml`:

```bash
# Kirkirar bayanan martaba na sirri kuma shiga
omi --profile personal auth login

# Bayanan martaba na aiki
omi --profile work auth login

# Gudanar da umarnin a karkashin bayanan martaba
omi --profile work memory list

# Bayanan martaba na gwaji da tashar API ta daban
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## 9. Tsaro da Ayyuka Mafi Kyau (Security Best Practices)

* **Kar a taba saka maɓallin API a cikin ma'ajiyar kode (git repo):** yi amfani da manajojin sirri ko fayilolin `.env` da `.gitignore` ta rufe.
* **Tarihin shell:** a kan kwamfutocin da aka raba, kar ka saka maɓallin kai tsaye a layin umarni; yi amfani da shiga hulɗa ko `OMI_API_KEY`.
* **Izuni na babban fayil:** iyakance izinin babban fayil ɗin tsari `~/.omi/` akan tsarin Unix (`chmod 700 ~/.omi`).
