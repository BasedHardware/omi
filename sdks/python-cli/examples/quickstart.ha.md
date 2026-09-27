# Jagorar farawa cikin sauri ta omi-cli (Hausa Quickstart)

> Jagora mai amfani don aiki da Omi kai tsaye daga terminal — ga masu haɓaka manhaja da AI agent masu cin gashin kansu.

`omi-cli` ita ce command-line interface ta hukuma ta developer API na [Omi](https://omi.me). Tana ba ka damar sarrafa manyan sassa huɗu na tsarin cikin tsari da hanyar da za a iya sarrafa ta kai tsaye: tunani (memories), tattaunawa (conversations), abubuwan aiki (action items) da manufofi (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Takardun hukuma:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Lambar tushe:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Sunayen umarni, zaɓuɓɓuka da saƙonnin shirin sun kasance da Turanci; bayanin wannan jagorar ne kawai da Hausa. README na Turanci shi ne babban tushe.

---

## 1. Shigarwa

Don guje wa rikice-rikicen dependency da gudanar da CLI a cikin keɓaɓɓen muhalli, ana ba da shawarar `pipx`:

```bash
# Shawara: keɓaɓɓen shigarwa da pipx
pipx install omi-cli

# Madadin: da pip a cikin Python virtual environment da aka kunna
pip install omi-cli
```

> **Lura: Sunan package da sunan umarni**
> * Sunan package a PyPI shi ne **`omi-cli`** (sunan `omi` na wani package ne da bai da alaƙa).
> * Umarnin da kake gudanarwa a terminal shi ne **`omi`** kawai.

Tabbatar cewa shigarwar tana aiki:

```bash
omi --version
omi --help
```

Idan terminal bai sami `omi` ba, tabbatar cewa virtual environment yana kunne ko kuma babban fayil da `pipx` ke ajiye fayilolin aiwatarwa yana cikin `PATH` ɗinka.

---

## 2. Tabbatar da shaida (Authentication)

`omi-cli` yana goyon bayan manyan hanyoyin tabbatarwa guda biyu:

| Hanya | Amfani | Misali |
| :--- | :--- | :--- |
| **Maɓallin API na developer (`omi_dev_*`)** | Script, CI/CD, sabar marasa allo, AI agent | `omi auth login --api-key ...` ko `OMI_API_KEY` |
| **OAuth na browser (Google/Apple)** | Kwamfutocin aiki na gida da masu haɓakawa | `omi auth login --browser` (Google) / `--provider apple` |

### Shiga ta hanyar tattaunawa
Gudanar ba tare da wani flag ba don zaɓar hanya ta hanyar tattaunawa:

```bash
omi auth login
# 1) Browser — yana buɗe browser don shiga da Google (yi amfani da `--provider apple` don Apple)
# 2) API key — manna maɓallin API daga app.omi.me (an ɓoye abin da ka shigar)
```

### Shiga kai tsaye ta browser
```bash
# Tsoho: shiga da Google
omi auth login --browser

# Madadin: shiga da Apple
omi auth login --browser --provider apple
```

### Amfani da maɓallin API na developer
Ƙirƙiri maɓalli a [app.omi.me](https://app.omi.me) ƙarƙashin **Developer → API Keys**:

```bash
# Ajiye maɓallin a cikin profile na gida da ke aiki
omi auth login --api-key omi_dev_token_ɗinka_na_gaskiya

# Ko kuma saita shi a matsayin environment variable (mafi kyau ga container da CI/CD)
export OMI_API_KEY="omi_dev_token_ɗinka_na_gaskiya"
```

> Ana amfani da `OMI_API_KEY` ne kawai idan profile mai aiki ba shi da maɓallin da aka ajiye. Idan ka riga ka shiga da `omi auth login` kuma kana son environment variable ya yi aiki, fara gudanar da `omi auth logout`.

### Duba matsayin tabbatarwa
* `omi auth status`: yana nuna profile mai aiki da shaidar da aka ɓoye (yana aiki a gida/ba tare da hanyar sadarwa ba; ranar ƙarewa tana shafar token na OAuth kawai).
* `omi auth whoami`: yana aika buƙata zuwa sabar Omi don tabbatar da inganci (yana buƙatar hanyar sadarwa).

```bash
omi auth status
omi auth whoami
```

`omi auth refresh` na nufin sabunta token na OAuth ba tare da sake shiga ba, amma babu wata hanyar shiga a yau — har da ta browser — da take samar da profile irin na OAuth: shiga ta browser (`--browser`) tana ajiye maɓallin API mai dorewa, kamar dai shiga ta maɓallin API kai tsaye.

```bash
omi auth refresh
```

> Saboda haka, a yanzu, gudanar da `omi auth refresh` a kan kowane profile yana ƙarewa da saƙon «Nothing to refresh» da exit code `1` — umarnin yana nan don profile irin na OAuth na gaba.

Fita:
```bash
omi auth logout
# Idan an saita OMI_API_KEY a cikin muhalli, cire shi ma (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Manyan umarni

### Tunani (Memories)
Tsararrun bayanai da lura na mahallin da Omi ya adana:

```bash
# Jera tunani
omi memory list

# Ƙirƙiri sabon tunani da rukuni
omi memory create "Na fi son gajerun amsoshi na fasaha da misalan Python" --category work

# Ɗauko takamaiman tunani ta ID
omi memory get <MEMORY_ID>
```

### Tattaunawa (Conversations)
Rikodin murya, rubutattun kwafi da tattaunawar da na'urorin Omi suka rubuta:

```bash
# Jera tattaunawa 5 na ƙarshe
omi conversation list --limit 5

# Ɗauko cikakkun bayanan tattaunawa tare da cikakken kwafi
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Abubuwan aiki (Action Items)
Ayyukan da aka ciro ta atomatik daga tattaunawa:

```bash
# Jera abubuwan aiki da ba a kammala ba
omi action-item list --open

# Yi wa abin aiki alamar an kammala
omi action-item complete <ACTION_ITEM_ID>
```

### Manufofi (Goals)
Alamun ci gaba da manufofi na dogon lokaci:

```bash
# Jera manufofi masu aiki
omi goal list

# Ƙirƙiri sabuwar manufa ta lamba
omi goal create "Sha ruwa lita 2 kowace rana" --type numeric --target 2 --unit liters

# Sabunta ƙimar yanzu ta manufa (ID da sabuwar ƙima)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. Tsararren aiki ta atomatik da fitarwar JSON (`--json`)

An gina `omi-cli` don aiki ta atomatik a cikin pipeline da toolchain. Flag na duniya `--json` yana dawo da JSON mai tsafta wanda na'ura za ta iya karantawa:

```bash
# Jera tunani a matsayin JSON kuma tace da jq
omi --json memory list | jq '.[] | {id, content, category}'

# Ɗauko taken tattaunawar kwanan nan
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Duba dukkan abubuwan aiki da ba a kammala ba a matsayin JSON ɗanye
omi --json action-item list --open | jq '.'
```

> **Muhimmiyar ƙa'idar rubutu:**
> `--json` **zaɓi ne na duniya** kuma dole ne a sanya shi **kafin** subcommand:
> * Daidai: `omi --json memory list`
> * Kuskure: `omi memory list --json`

### Raba shafuka (Pagination)
Yawancin umarnin `list` (misali `memory`, `conversation`, `action-item`) suna goyon bayan `--limit` da `--offset`; `goal list` yana goyon bayan `--limit` kawai (da kuma `--include-inactive`), ba `--offset` ba:

```bash
omi --json memory list --limit 50 --offset 50
```

### Fitarwa zuwa fayil
Don hana launukan ANSI ko haruffan sarrafawa gurɓata fayil, karkatar da stdout kai tsaye a cikin shell:

```bash
# Fitar da tunani kai tsaye zuwa fayil na JSON mai tsafta
omi --json memory list > memories.json
```

---

## 5. Lambobin fita (Exit Codes Contract)

Don sarrafa kurakurai abin dogaro a CI/CD da script, `omi-cli` yana bin tsayayyen yarjejeniyar lambobin fita (duba `omi_cli/errors.py`):

| Lamba | Suna | Bayani da misali |
| :---: | :--- | :--- |
| `0` | **Nasara (`EXIT_OK`)** | Aikin ya kammala ba tare da kuskure ba. |
| `1` | **Kuskuren amfani (`EXIT_USAGE`)** | Kurakuran tabbatarwa na omi-cli kansa: `--browser` da `--api-key` da ba za a haɗa su ba, zaɓi mara inganci a shiga ta tattaunawa, shigarwa mara komai daga stdin, ko `omi auth refresh` a kan profile na maɓallin API. |
| `2` | **Kuskuren tabbatarwa (`EXIT_AUTH`)** | Shaida ta ɓace ko mara inganci, ko zaman da ya ƙare. Lura: flag da ba a sani ba ko argument da ya ɓace shi ma Click da kansa yake ƙi shi kuma yana fita da lamba `2`. |
| `3` | **Kuskuren sabar (`EXIT_SERVER`)** | HTTP 5xx daga sabar Omi ko yankewar hanyar sadarwa. |
| `4` | **Iyakar gudu (`EXIT_RATE_LIMITED`)** | HTTP 429 — buƙatu da yawa cikin ɗan gajeren lokaci. |
| `5` | **Ba a samu ba (`EXIT_NOT_FOUND`)** | HTTP 404 — abin da aka nema (tunani, tattaunawa, abin aiki) babu shi. |

---

## 6. Misalai ga shell daban-daban

### Bash / Zsh (Linux / macOS)
```bash
# Saita maɓallin API na wannan zaman
export OMI_API_KEY="omi_dev_token_ɗinka_na_gaskiya"

# Gudanar da umarni kuma duba lambar fita
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Kuskure wajen ɗauko tunani daga Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# Ayyana environment variable a PowerShell
$env:OMI_API_KEY = "omi_dev_token_ɗinka_na_gaskiya"

# Mayar da fitarwar JSON kai tsaye zuwa PowerShell object
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Duba kuskure da $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Umarnin Omi ya gaza da lambar fita $LASTEXITCODE."
}
```

---

## 7. Haɗin API na Desktop na gida (Omi Desktop)

Lokacin da Omi Desktop ke gudana a na'urarka (tsohon port 47778), za ka iya aiki kai tsaye da mahallin gida ba tare da wucewa ta cloud ba:

```bash
# Saita haɗin API na gida (yi amfani da environment variable don kare token)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Shigar da token na Desktop: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Tabbatar da matsayin haɗin gida
omi --json local status

# Bincika tarihin allon gida
omi --json local search-screen "Rahoton kwata" --days 7 --app Safari
```

Maimakon environment variable za ka iya ajiye saitunan a profile: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Sarrafa profile da yawa (Profiles)

Yi amfani da `--profile` don sauya tsakanin asusun kai, profile na aiki ko muhallin gwaji cikin sauƙi. Ana ajiye saitunan a `~/.omi/config.toml`. Tsarin fifiko: flag na `--profile`, sannan environment variable `OMI_PROFILE`, sannan a ƙarshe profile mai aiki da aka ajiye (darajarsa ta farko ita ce `default`, amma kowace `auth login` tana sabunta wanda profile ke aiki).

```bash
# Ƙirƙiri kuma shiga profile na kai
omi --profile personal auth login

# Ƙirƙiri kuma shiga profile na aiki
omi --profile work auth login

# Gudanar da umarni da takamaiman profile
omi --profile work memory list

# Zaɓi profile ta environment variable
export OMI_PROFILE=work
omi memory list

# Yi amfani da endpoint na musamman don gwaji
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Jagororin tsaro da mafi kyawun hanyoyi

* **Kada ka rubuta maɓallai a cikin lamba:** Kada ka taɓa yin commit na maɓallan API (`omi_dev_*`) zuwa Git repository. Yi amfani da fayilolin `.env` da ke cikin `.gitignore` ko amintattun manajojin sirri.
* **Kare tarihin shell:** A kan sabar da ake rabawa, kada ka ba da maɓallai a matsayin argument na command-line a fili; yi amfani da shiga ta tattaunawa ko `OMI_API_KEY`.
* **Taƙaita izinin babban fayil:** A Unix/macOS, tabbatar cewa babban fayil ɗin saitin yana da iyakantaccen izini:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Tsaftace zaman:** Lokacin rushe muhallin wucin gadi, ka tuna ka cire environment variable:
  ```bash
  unset OMI_API_KEY
  ```
