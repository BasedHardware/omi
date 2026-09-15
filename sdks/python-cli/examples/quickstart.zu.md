# Umhlahlandlela wokuqala ngokushesha we-omi-cli (Zulu Quickstart)

> Umhlahlandlela osebenzayo wokusebenza ne-Omi ngqo kusuka ku-terminal — wabathuthukisi nama-AI agent azimele.

I-`omi-cli` iyi-command-line interface esemthethweni ye-developer API ye-[Omi](https://omi.me). Ikuvumela ukuthi uphathe izingxenye ezine eziyisisekelo zesistimu ngendlela ehlelekile nengenziwa ngokuzenzakalela: izinkumbulo (memories), izingxoxo (conversations), izinto zokwenza (action items) nemigomo (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Amadokhumenti asemthethweni:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Ikhodi yomthombo:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

Amagama emiyalo, izinketho nemilayezo yohlelo ahlala esiNgisini; umbhalo wencazelo walo mhlahlandlela kuphela oseZulwini. I-README yesiNgisi iyisisekelo esiyinhloko.

---

## 1. Ukufaka

Ukugwema ukungqubuzana kwe-dependency nokusebenzisa i-CLI endaweni ehlukanisiwe, kunconywa i-`pipx`:

```bash
# Okunconyiwe: ukufaka okuhlukanisiwe nge-pipx
pipx install omi-cli

# Enye indlela: nge-pip ngaphakathi kwe-Python virtual environment evuliwe
pip install omi-cli
```

> **Qaphela: Igama le-package negama lomyalo**
> * Igama le-package ku-PyPI ngu-**`omi-cli`** (igama elithi `omi` elinye i-package engahlobene).
> * Umyalo owusebenzisa ku-terminal ngu-**`omi`** kuphela.

Qinisekisa ukuthi ukufaka kuyasebenza:

```bash
omi --version
omi --help
```

Uma i-terminal ingayitholi i-`omi`, hlola ukuthi i-virtual environment ivuliwe noma ukuthi ifolda lapho i-`pipx` ibeka khona amafayela asebenzayo ikwi-`PATH` yakho.

---

## 2. Ukuqinisekisa ubunikazi (Authentication)

I-`omi-cli` isekela izindlela ezimbili eziyinhloko zokuqinisekisa:

| Indlela | Ukusetshenziswa | Isibonelo |
| :--- | :--- | :--- |
| **Ukhiye we-API womthuthukisi (`omi_dev_*`)** | Ama-script, i-CI/CD, amaseva angenasikrini, ama-AI agent | `omi auth login --api-key ...` noma `OMI_API_KEY` |
| **I-OAuth yesiphequluli (Google/Apple)** | Izikhungo zokusebenza zendawo nabathuthukisi | `omi auth login --browser` (Google) / `--provider apple` |

### Ukungena okusebenzisanayo
Sebenzisa ngaphandle kwe-flag ukuze ukhethe indlela ngokusebenzisana:

```bash
omi auth login
# 1) Browser — ivula isiphequluli sokungena nge-Google (sebenzisa `--provider apple` ye-Apple)
# 2) API key — namathisela ukhiye we-API osuka ku-app.omi.me (okufakiwe kufihliwe)
```

### Ukungena ngqo ngesiphequluli
```bash
# Okuzenzakalelayo: ukungena nge-Google
omi auth login --browser

# Enye indlela: ukungena nge-Apple
omi auth login --browser --provider apple
```

### Ukusebenzisa ukhiye we-API womthuthukisi
Dala ukhiye ku-[app.omi.me](https://app.omi.me) ngaphansi kwe-**Developer → API Keys**:

```bash
# Gcina ukhiye kuphrofayili yendawo esebenzayo
omi auth login --api-key omi_dev_ithokheni_yakho_yangempela

# Noma usethe njenge-environment variable (kungcono kuma-container ne-CI/CD)
export OMI_API_KEY="omi_dev_ithokheni_yakho_yangempela"
```

> I-`OMI_API_KEY` isetshenziswa kuphela uma iphrofayili esebenzayo ingenawo ukhiye ogciniwe. Uma usungenile nge-`omi auth login` futhi ufuna ukuthi i-environment variable isebenze, qala usebenzise `omi auth logout`.

### Ukuhlola isimo sokuqinisekisa
* `omi auth status`: ibonisa iphrofayili esebenzayo nezimfanelo ezifihliwe (isebenza endaweni/ngaphandle kwenethiwekhi; usuku lokuphelelwa yisikhathi lusebenza kuphela kumathokheni e-OAuth).
* `omi auth whoami`: ithumela isicelo kuseva ye-Omi ukuqinisekisa ukusebenza (idinga inethiwekhi).

```bash
omi auth status
omi auth whoami
```

Vuselela ithokheni ye-OAuth ngaphandle kokungena futhi:

```bash
omi auth refresh
```

> I-`omi auth refresh` isebenza kuphela kumaphrofayili angene ngesiphequluli (OAuth). Kumaphrofayili asekelwe kukhiye we-API akukho okuvuselelwayo, futhi umyalo uphela ngomlayezo othi «Nothing to refresh» ne-exit code `1`.

Ukuphuma:
```bash
omi auth logout
# Uma i-OMI_API_KEY isethiwe kwi-environment, yisuse nayo (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Imiyalo eyinhloko

### Izinkumbulo (Memories)
Amaqiniso ahlelekile nokubonwa kwesimo okugcinwe yi-Omi:

```bash
# Faka uhlu lwezinkumbulo
omi memory list

# Dala inkumbulo entsha nesigaba
omi memory create "Ngithanda izimpendulo ezimfushane zobuchwepheshe ezinezibonelo ze-Python" --category work

# Thola inkumbulo ethile nge-ID
omi memory get <MEMORY_ID>
```

### Izingxoxo (Conversations)
Okuqoshiwe kwezwi, imibhalo nezingxoxo ezirekhodwe amadivayisi e-Omi:

```bash
# Faka uhlu lwezingxoxo ezi-5 zokugcina
omi conversation list --limit 5

# Thola imininingwane yengxoxo kanye nombhalo ophelele
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Izinto zokwenza (Action Items)
Imisebenzi ekhishwe ngokuzenzakalela ezingxoxweni:

```bash
# Faka uhlu lwezinto zokwenza ezivuliwe
omi action-item list --open

# Maka into yokwenza njengeqediwe
omi action-item complete <ACTION_ITEM_ID>
```

### Imigomo (Goals)
Izinkomba zenqubekela phambili nemigomo yesikhathi eside:

```bash
# Faka uhlu lwemigomo esebenzayo
omi goal list

# Dala umgomo omusha wezinombolo
omi goal create "Phuza amalitha amanzi angu-2 nsuku zonke" --type numeric --target 2 --unit liters

# Buyekeza inani lamanje lomgomo (i-ID nenani elisha)
omi goal progress <GOAL_ID> 1.5
```

---

## 4. Ukuzenzakalela okuhlelekile nokukhipha i-JSON (`--json`)

I-`omi-cli` yakhelwe ukuzenzakalela kuma-pipeline nama-toolchain. I-flag yomhlaba wonke ethi `--json` ibuyisela i-JSON ehlanzekile efundeka ngomshini:

```bash
# Faka uhlu lwezinkumbulo njenge-JSON bese uhlunga nge-jq
omi --json memory list | jq '.[] | {id, content, category}'

# Thola izihloko zezingxoxo zakamuva
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Buka zonke izinto zokwenza ezivuliwe njenge-JSON eluhlaza
omi --json action-item list --open | jq '.'
```

> **Umthetho obalulekile we-syntax:**
> I-`--json` **iyinketho yomhlaba wonke** futhi kufanele ibekwe **ngaphambi** kwe-subcommand:
> * Okulungile: `omi --json memory list`
> * Okungalungile: `omi memory list --json`

### Ukwahlukanisa amakhasi (Pagination)
Imiyalo ye-`list` isekela i-`--limit` ne-`--offset`:

```bash
omi --json memory list --limit 50 --offset 50
```

### Ukukhiphela efayelini
Ukuvimbela imibala ye-ANSI noma izinhlamvu zokulawula ukungcolisa ifayela, qondisa i-stdout ngqo ku-shell:

```bash
# Khiphela izinkumbulo ngqo efayelini le-JSON elihlanzekile
omi --json memory list > memories.json
```

---

## 5. Amakhodi okuphuma (Exit Codes Contract)

Ukuphatha amaphutha okuthembekile ku-CI/CD nakuma-script, i-`omi-cli` ilandela isivumelwano esiqinile samakhodi okuphuma (bheka i-`omi_cli/errors.py`):

| Ikhodi | Igama | Incazelo nesibonelo |
| :---: | :--- | :--- |
| `0` | **Impumelelo (`EXIT_OK`)** | Umsebenzi uqedwe ngaphandle kwephutha. |
| `1` | **Iphutha lokusebenzisa (`EXIT_USAGE`)** | Amaphutha okuqinisekisa e-omi-cli uqobo: i-`--browser` ne-`--api-key` ezingahambisani, ukukhetha okungalungile ekungeneni okusebenzisanayo, okufakiwe okungenalutho okusuka ku-stdin, noma i-`omi auth refresh` kuphrofayili yokhiye we-API. |
| `2` | **Iphutha lokuqinisekisa (`EXIT_AUTH`)** | Izimfanelo ezingekho noma ezingalungile, noma iseshini ephelelwe yisikhathi. Qaphela: i-flag engaziwa noma i-argument engekho nayo yenqatshwa yi-Click uqobo futhi iphuma ngekhodi `2`. |
| `3` | **Iphutha leseva (`EXIT_SERVER`)** | I-HTTP 5xx evela kuseva ye-Omi noma ukuphazamiseka kwenethiwekhi. |
| `4` | **Umkhawulo wesilinganiso (`EXIT_RATE_LIMITED`)** | I-HTTP 429 — izicelo eziningi kakhulu esikhathini esifushane. |
| `5` | **Akutholakalanga (`EXIT_NOT_FOUND`)** | I-HTTP 404 — insiza eceliwe (inkumbulo, ingxoxo, into yokwenza) ayikho. |

---

## 6. Izibonelo zama-shell ahlukene

### Bash / Zsh (Linux / macOS)
```bash
# Setha ukhiye we-API waleseshini
export OMI_API_KEY="omi_dev_ithokheni_yakho_yangempela"

# Sebenzisa umyalo bese uhlola ikhodi yokuphuma
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Iphutha ekutholeni izinkumbulo ku-Omi." >&2
fi
```

### PowerShell (Windows)
```powershell
# Chaza i-environment variable ku-PowerShell
$env:OMI_API_KEY = "omi_dev_ithokheni_yakho_yangempela"

# Guqula okukhishwayo kwe-JSON ngqo kube yi-PowerShell object
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Hlola iphutha nge-$LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Umyalo we-Omi wehlulekile ngekhodi yokuphuma $LASTEXITCODE."
}
```

---

## 7. Ukuhlanganisa i-API ye-Desktop yendawo (Omi Desktop)

Lapho i-Omi Desktop isebenza kumshini wakho (i-port ezenzakalelayo 47778), ungasebenza ngqo nesimo sendawo ngaphandle kokudlula ku-cloud:

```bash
# Lungisa ukuxhumana kwe-API yendawo (sebenzisa ama-environment variable ukuvikela ithokheni)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Faka ithokheni ye-Desktop: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Qinisekisa isimo sokuxhumana kwendawo
omi --json local status

# Sesha emlandweni wesikrini sendawo
omi --json local search-screen "Umbiko wekota" --days 7 --app Safari
```

Esikhundleni sama-environment variable ungagcina izilungiselelo kuphrofayili: `omi local configure --url http://127.0.0.1:47778 --token ...`.

---

## 8. Ukuphatha amaphrofayili amaningi (Profiles)

Sebenzisa i-`--profile` ukushintsha kalula phakathi kwe-akhawunti yakho siqu, iphrofayili yomsebenzi noma indawo yokuhlola. Izilungiselelo zigcinwa ku-`~/.omi/config.toml`. Ukulandelana kokubaluleka: i-flag ye-`--profile`, bese i-environment variable ye-`OMI_PROFILE`, bese ekugcineni iphrofayili ye-`default`.

```bash
# Dala bese ungena kuphrofayili yakho siqu
omi --profile personal auth login

# Dala bese ungena kuphrofayili yomsebenzi
omi --profile work auth login

# Sebenzisa umyalo ngephrofayili ethile
omi --profile work memory list

# Khetha iphrofayili nge-environment variable
export OMI_PROFILE=work
omi memory list

# Sebenzisa i-endpoint yangokwezifiso yokuhlola
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Imihlahlandlela yokuphepha nezinqubo ezingcono kakhulu

* **Ungabhali okhiye ekhodini:** Ungalokothi wenze i-commit yokhiye be-API (`omi_dev_*`) ku-Git repository. Sebenzisa amafayela e-`.env` akwi-`.gitignore` noma abaphathi bezimfihlo abaphephile.
* **Vikela umlando we-shell:** Kumaseva abiwayo, ungadluli okhiye njengama-argument e-command-line obala; sebenzisa ukungena okusebenzisanayo noma i-`OMI_API_KEY`.
* **Nciphisa izimvume zefolda:** Ku-Unix/macOS, qinisekisa ukuthi ifolda lokulungiselela linezimvume ezikhawulelwe:
  ```bash
  chmod 700 ~/.omi
  chmod 600 ~/.omi/config.toml 2>/dev/null || true
  ```
* **Ukuhlanza iseshini:** Lapho ususa izindawo zesikhashana, khumbula ukususa i-environment variable:
  ```bash
  unset OMI_API_KEY
  ```
