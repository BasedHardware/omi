# Gwida għal Bidu Mgħaġġel ta' omi-cli (Maltese Quickstart)

> Gwida prattika biex tikkomunika ma' Omi direttament mit-terminal tiegħek — iddisinjata għal żviluppaturi u aġenti awtonomi tal-IA.

`omi-cli` hija l-interface tal-linja tal-kmand uffiċjali għall-API tal-iżviluppaturi ta' [Omi](https://omi.me). Tipprovdi aċċess strutturat u orjentat lejn l-aġenti għall-erba' riżorsi ewlenin ta' Omi: **memorji** (memories), **konversazzjonijiet** (conversations), **kompiti/azzjonijiet** (action items), u **għanijiet** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentazzjoni Uffiċjali:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kodiċi tas-Sors:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installazzjoni

Biex tevita kunflitti ma' pakketti oħra u żżomm ambjent separat u stabbli, l-użu ta' `pipx` huwa rakkomandat ħafna:

```bash
# Metodu rakkomandat: installazzjoni iżolata b'pipx
pipx install omi-cli

# Installazzjoni alternattiva permezz ta' pip standard (eż. f'ambjent virtwali)
pip install omi-cli
```

> **Distinzjoni Importanti: Isem tal-Pakkett vs Isem tal-Kmand**
> * L-isem tal-pakkett fuq PyPI huwa **`omi-cli`** (il-pakkett `omi` huwa proġett separat u differenti).
> * Il-kmand eżekutibbli fit-terminal tiegħek huwa sempliċement: **`omi`**.

Ivverifika li l-installazzjoni rnexxiet billi tivverifika l-verżjoni u l-menu ta' għajnuna:

```bash
omi --version
omi --help
```

---

## 2. Awtentikazzjoni (Authentication)

`omi-cli` jappoġġja żewġ metodi ewlenin ta' dħul:

| Metodu | Użu Prinċipali | Kmand / Konfigurazzjoni |
| :--- | :--- | :--- |
| **Ċavetta tal-API (`omi_dev_*`)** | CI/CD, servers mingħajr skrin (headless), aġenti tal-IA | `omi auth login --api-key ...` jew `OMI_API_KEY` |
| **Dħul permezz ta' Browser (Google/Apple)** | Żvilupp lokali fuq il-kompjuter personali tiegħek | `omi auth login --browser` (Google) / `--provider apple` |

### Dħul Interattiv
Jekk tħaddem il-kmand mingħajr parametri oħra, jidher menu interattiv:

```bash
omi auth login
# 1) Browser — Idħol permezz ta' Google fuq il-browser (żid `--provider apple` għal Apple)
# 2) API key — Daħħal ċavetta tal-iżviluppatur maħluqa minn app.omi.me
```

### Dħul Dirett bil-Browser
```bash
# Dħul standard b'kont ta' Google
omi auth login --browser

# Dħul b'kont ta' Apple
omi auth login --browser --provider apple
```

### Dħul b'Ċavetta tal-API
Oħloq ċavetta tal-API mid-dashboard ta' [app.omi.me](https://app.omi.me) taħt is-sezzjoni **Developer → API Keys** (prefiss `omi_dev_*`):

```bash
# Issejvja ċ-ċavetta fil-profil lokali attiv
omi auth login --api-key omi_dev_ic_cavetta_tieghek

# Jew permezz ta' varjabbli tal-ambjent (ideali għal containers Docker u skripts awtomatizzati):
# Nota: jekk il-profil attiv diġà għandu ċavetta maħżuna, l-ewwel ħaddem `omi auth logout`.
export OMI_API_KEY="omi_dev_ic_cavetta_tieghek"
```

> **Nota dwar `omi auth refresh`:** L-aġġornament tat-token b'`omi auth refresh` jaħdem biss għal sessjonijiet tal-browser (OAuth). Għal profili b'ċavetta tal-API, iċ-ċwievet huma statiċi u l-kmand ma jwettaq l-ebda azzjoni.

### Verifika tal-Istat tas-Sessjoni
* `omi auth status`: Juri l-profil attiv u ċ-ċavetta mgħottija mingħajr talbiet fuq l-internet (jaħdem offline).
* `omi auth whoami`: Jagħmel talba diretta lis-server ta' Omi biex jivvalida s-sessjoni u l-identità tiegħek (jeħtieġ internet).

```bash
omi auth status
omi auth whoami
```

### Ħruġ mis-Sistema (Logout)
```bash
omi auth logout
# Jekk użajt il-varjabbli tal-ambjent OMI_API_KEY, neħħiha mis-sessjoni kurrenti:
unset OMI_API_KEY
```

---

## 3. Kmandi Prinċipali

### Memorji (Memories)
Fatti, noti u kuntest maħżuna minn Omi dwarek:

```bash
# Uri l-memorji salvati kollha
omi memory list

# Oħloq memorja ġdida b'kategorija
omi memory create "Jippreferi spjegazzjonijiet tekniċi qosra u eżempji f'Python" --category work

# Ikseb memorja partikolari permezz tal-ID tagħha
omi memory get <ID_TAL_MEMORJA>
```

### Konversazzjonijiet (Conversations)
Skambji ta' vuċi u traskrizzjonijiet ipproċessati mill-apparat Omi:

```bash
# Uri l-aħħar 5 konversazzjonijiet
omi conversation list --limit 5

# Ikseb konversazzjoni flimkien mat-traskrizzjoni sħiħa
omi conversation get <ID_TAL_KONVERSAZZJONI> --include-transcript
```

### Oġġetti ta' Azzjoni (Action Items)
Kompiti u segwiti skoperti awtomatikament mill-konversazzjonijiet:

```bash
# Uri l-kompiti miftuħa
omi action-item list --open

# Immarka kompitu bħala mitmum
omi action-item complete <ID_TAL_KOMPITU>
```

### Għanijiet (Goals)
Traċċar tal-progress u għanijiet personali:

```bash
# Uri l-għanijiet attivi kollha
omi goal list

# Oħloq għan numeriku ġdid
omi goal create "Ixrob 2 litri ilma kuljum" --type numeric --target 2 --unit liters

# Aġġorna l-progress ta' għan
omi goal progress <ID_TAL_GHAN> 1
```

---

## 4. Awtomazzjoni Strutturata u Output JSON (`--json`)

`omi-cli` huwa mibni b'moħħu fuq l-integrazzjoni fi skripts u aġenti intelliġenti. Il-parametru globali `--json` jipproduċi output JSON standard li jista' jiġi ffiltrat faċilment b'għodod bħal `jq`:

```bash
# Elenka l-memorji f'format JSON u ffiltra b'jq
omi --json memory list | jq '.[] | {id, content, category}'

# Oħroġ it-titli u l-ħinijiet tal-aħħar konversazzjonijiet
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Uri l-kompiti miftuħa f'format JSON mhux ipproċessat
omi --json action-item list --open | jq '.'
```

> **Regola Ewlenija tal-Parametru:**
> `--json` huwa parametru **globali**, u għalhekk irid jitqiegħed **qabel** is-sottokmand:
> * Korrett: `omi --json memory list`
> * Mhux korrett: `omi memory list --json`

### Paġinazzjoni u Esportazzjoni f'Fajls
Ikkontrolla l-volum ta' dejta li tirċievi billi tuża `--limit` u `--offset`:

```bash
# Qassam ir-riżultati f'paġni lejn fajls lokali
omi --json memory list --limit 25 --offset 0 > memorji_p1.json
omi --json memory list --limit 25 --offset 25 > memorji_p2.json
```

---

## 5. Kodiċijiet tal-Ħruġ (Exit Codes)

Kuntratt formali tal-kodiċijiet skont `omi_cli/errors.py` għall-immaniġġjar sigur tal-iżbalji fi skripts:

| Kodiċi | Isem Uffiċjali | Deskrizzjoni u Kawża |
| :---: | :--- | :--- |
| `0` | `EXIT_OK` | Il-kmand tlesta b'suċċess sħiħ. |
| `1` | `EXIT_USAGE` | Żball intern ta' validazzjoni ta' `omi-cli` (eż. `--browser` u `--api-key` flimkien, għażliet mhux validi). *(Nota: argumenti mhux magħrufa ta' Click joħorġu b'kodiċi 2).* |
| `2` | `EXIT_AUTH` | Żball fl-awtentikazzjoni, ċavetta/token nieqes jew skadut, jew żball ta' analiżi ta' Click. |
| `3` | `EXIT_SERVER` | Żball fis-server tal-API (HTTP 5xx) jew problema fil-konnessjoni tan-netwerk. |
| `4` | `EXIT_RATE_LIMITED` | Qbiż tal-limitu ta' talbiet (HTTP 429; il-klijent jerġa' jipprova skont `Retry-After`). |
| `5` | `EXIT_NOT_FOUND` | Ir-riżors mitlub ma nstabx fuq l-API (HTTP 404). |

---

## 6. Eżempji ta' Skripts f'Terminals Differenti

### Bash / Zsh (Linux u macOS)
```bash
export OMI_API_KEY="omi_dev_ic_cavetta_tieghek"

# Ħaddem il-kmand u vverifika l-kodiċi tal-ħruġ
omi --json memory list --limit 10
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Il-memorji nġiebu b'suċċess."
elif [ $EXIT_CODE -eq 2 ]; then
    echo "Żball fl-awtentikazzjoni: iċċekkja OMI_API_KEY jew idħol mill-ġdid." >&2
else
    echo "Il-kmand falla bil-kodiċi: $EXIT_CODE" >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_ic_cavetta_tieghek"

# Ikkonverti l-output JSON f'oġġett nattiv ta' PowerShell
$memorji = omi --json memory list | ConvertFrom-Json
$memorji | Select-Object id, content, category

# Iċċekkja għal żbalji permezz ta' $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Il-kmand ta' Omi falla b'kodiċi ta' ħruġ: $LASTEXITCODE"
}
```

---

## 7. Integrazzjoni mal-API Lokali tad-Desktop (Local Desktop API)

Jekk l-applikazzjoni Omi tad-Desktop tkun qed taħdem fuq l-istess kompjuter, tista' tistaqsi l-kronoloġija tal-iskrin lokalment mingħajr ma tuża l-cloud:

```bash
# Issettja l-indirizz u t-token lokali
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Daħħal it-token lokali tad-desktop: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Ivverifika l-istat tas-servizz lokali
omi --json local status

# Fittex fl-attività riċenti tal-iskrin
omi --json local search-screen "Rapport Finanzjarju" --days 3 --app Chrome
```

---

## 8. Ġestjoni ta' Profili Multipli (Profiles)

Il-parametru `--profile` jippermettilek li żżomm profili separati (eż. personali, xogħol, jew ambjent tat-test). Il-konfigurazzjoni tinħażen f'`~/.omi/config.toml`:

```bash
# Idħol f'profili differenti
omi --profile personali auth login
omi --profile xoghol auth login

# Ħaddem kmandi taħt profil speċifiku
omi --profile xoghol memory list

# Qabbad mal-ambjent tat-testijiet (staging)
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Sigurtà u l-Aħjar Prattiki

* **Tpoġġix ċwievet f'Git:** Qatt ma ddaħħal ċwievet `omi_dev_*` f'repożitorji pubbliċi tal-kodiċi; uża varjabbli tal-ambjent jew maniġer tas-sigrieti.
* **Permessi tal-Fajls fuq sistemi Unix:** Ipproteġi d-direttorju tal-konfigurazzjoni lokali b'permessi ristretti:
  ```bash
  chmod 700 ~/.omi
  ```
* **Tindif ta' Kredenzjali Temporanji:** Meta tlesti l-ħidma fuq magni kondiviżi jew servers temporanji, neħħi l-varjabbli b'`unset OMI_API_KEY` u oħroġ b'`omi auth logout`.
