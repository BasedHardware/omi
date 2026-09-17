# omi-cli Kiirjuhend (Estonian Quickstart)

> Praktiline juhend Omi kasutamiseks otse terminalist — loodud arendajatele ja autonoomsetele AI agentidele.

`omi-cli` on [Omi](https://omi.me) arendaja API ametlik käsurealiides (CLI). See pakub struktureeritud ligipääsu Omi neljale peamisele ressursile: mälestused (*memories*), vestlused (*conversations*), tegevusüksused (*action items*) ja eesmärgid (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Ametlik dokumentatsioon:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Lähtekood:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Paigaldamine

Isoleeritud keskkonna tagamiseks ja Pythoni süsteemsete sõltuvuste konfliktide vältimiseks on tungivalt soovitatav kasutada tööriista `pipx`:

```bash
# Soovitatav meetod: isoleeritud paigaldus pipx abil
pipx install omi-cli

# Alternatiivne paigaldus pip abil (nt virtuaalses keskkonnas)
pip install omi-cli
```

> **Oluline täpsustus: Paketi nimi vs käsu nimi**
> * Ametlik paketi nimi PyPI repositooriumis on **`omi-cli`** (pakett nimega `omi` on eraldiseisev ja mitteseotud projekt).
> * Terminalis käivitatav käsk on otse: **`omi`**.

Kontrollige paigalduse õnnestumist versiooni ja abiteabe kuvamisega:

```bash
omi --version
omi --help
```

---

## 2. Autentimine (Authentication)

`omi-cli` toetab kahte peamist autentimisviisi:

| Meetod | Kasutusvaldkond | Käsu näidis |
| :--- | :--- | :--- |
| **Arendaja API võti (`omi_dev_*`)** | Skriptid, CI/CD, serverid, AI agendid | `omi auth login --api-key ...` või `OMI_API_KEY` |
| **OAuth sisselogimine brauseris** | Kohalik arendus isiklikus arvutis | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktiivne sisselogimine

Käsu käivitamine ilma lisalippudeta avab interaktiivse menüü:

```bash
omi auth login
# 1) Browser — Sisselogimine veebibrauseri kaudu (Google või Apple)
# 2) API key — Arendaja võtme kleepimine aadressilt app.omi.me
```

### Sisselogimine veebibrauseri kaudu

```bash
# Vaikimisi sisselogimine Google kontoga
omi auth login --browser

# Alternatiivne sisselogimine Apple profiiliga
omi auth login --browser --provider apple
```

### Sisselogimine arendaja API võtmega

Genereerige API võti juhtpaneelilt [app.omi.me](https://app.omi.me) jaotises **Developer → API Keys**:

```bash
# Võtme salvestamine aktiivsesse kohalikku profiili
omi auth login --api-key omi_dev_teie_voti_siin

# Või keskkonnamuutuja eksportimisega (soovitatav Docker konteinerites ja CI/CD töövoogudes):
export OMI_API_KEY="omi_dev_teie_voti_siin"
```

> **Turvahoiatus ja prioriteet:**
> * Lipu `--api-key` kasutamine otse käsureal jätab võtme nähtavaks kesta ajaloos (`shell history`) ja protsesside nimekirjas. Avalikes masinates eelistage interaktiivset kleepimist (`omi auth login`) või keskkonnamuutujat `OMI_API_KEY`.
> * Kui aktiivses profiilis on juba salvestatud API võti, on see keskkonnamuutuja ees prioriteetne. Muutuja `OMI_API_KEY` aktiveerimiseks logige esmalt välja käsuga `omi auth logout` või looge uus profiil.

### Autentimise oleku kontroll

* `omi auth status`: Kuvab aktiivse profiili ja maskeeritud identifikaatori kohalikust konfiguratsioonist (töötab võrguühenduseta).
* `omi auth whoami`: Teeb võrgupäringu Omi serverisse sessiooni kehtivuse kontrollimiseks.

```bash
omi auth status
omi auth whoami
```

### Väljalogimine (Logout)

Kohalike autentimisandmete eemaldamiseks:

```bash
omi auth logout
# Kui kasutasite keskkonnamuutujat OMI_API_KEY, eemaldage see sessioonist:
unset OMI_API_KEY
```

> **Turvamärkus:** Konfiguratsioonifail asub teekonnal `~/.omi/config.toml`. Unixi süsteemides on soovitatav seada piiratud õigused: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Põhikäsud

### Mälestused (Memories)

Püsivate faktide, tähelepanekute ja konteksti salvestamine:

```bash
# Salvestatud mälestuste nimekiri
omi memory list

# Uue mälestuse loomine
omi memory create "Kasutaja eelistab lühikesi tehnilisi vastuseid Pythoni näidetega" --category work

# Konkreetse mälestuse pärimine identifikaatori järgi
omi memory get <MÄLESTUSE_ID>
```

### Vestlused (Conversations)

Omi seadmete salvestatud vestlused ja nende tekstilised transkriptsioonid:

```bash
# Viimase 5 vestluse nimekiri
omi conversation list --limit 5

# Vestluse pärimine koos täieliku transkriptsiooniga
omi conversation get <VESTLUSE_ID> --include-transcript
```

### Tegevusüksused ja ülesanded (Action Items)

Vestlustest automaatselt tuvastatud ja ekstraheeritud ülesanded:

```bash
# Avatud tegevusüksuste nimekiri
omi action-item list --open

# Ülesande märkimine tehtuks
omi action-item complete <ÜLESANDE_ID>
```

### Eesmärgid (Goals)

Pikaajaliste eesmärkide ja edusammude jälgimine:

```bash
# Aktiivsete eesmärkide nimekiri
omi goal list

# Uue numbrilise eesmärgi loomine (pealkiri antakse positsioonilise argumendina)
omi goal create "Päevane veetarbimine" --type numeric --target 2500 --unit "ml"
```

---

## 4. Struktureeritud automatiseerimine ja JSON väljund (`--json`)

`omi-cli` integreerub sujuvalt skriptidesse ja tehisintellekti agentide töövoogudesse. Globaalne lipp `--json` tagab puhta JSON-vormingu, mida saab töödelda selliste tööriistadega nagu `jq`:

```bash
# Mälestuste nimekiri JSON-vormingus ja filtreerimine jq abil
omi --json memory list | jq '.[] | {id, content, category}'

# Viimase 5 vestluse pealkirjade ekstraheerimine
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Avatud ülesannete nimekiri
omi --json action-item list --open | jq '.'
```

> **Kriitiline süntaksireegel:**
> Lipp `--json` on **globaalne valik**, mis tuleb alati paigutada **enne** alamkäsku:
> * Õige: `omi --json memory list`
> * Vale: `omi memory list --json`

### Lehekülgede jaotamine ja andmete eksportimine

Suurte andmehulkade töötlemisel kasutage parameetreid `--limit` ja `--offset`:

```bash
# Andmete hankimine lehekülgede kaupa
omi --json memory list --limit 25 --offset 0 > malestused-leht-1.json
omi --json memory list --limit 25 --offset 25 > malestused-leht-2.json
```

Faili suunamine loob või kirjutab kohaliku faili üle. Enne faili töötlemist kontrollige alati käsu väljumiskoodi. Veateated saadetakse standardveavoogu (`stderr`), seega tühi fail ei garanteeri andmete puudumist. Eksporditud failid võivad sisaldada tundlikke andmeid — kaitske neid vastavalt turvanõuetele.

---

## 5. Väljumiskoodid (Exit Codes Contract)

`omi-cli` järgib ranget väljumiskoodide lepingut usaldusväärseks veahalduseks skriptides ja CI/CD süsteemides (vastavalt failile `omi_cli/errors.py`):

| Kood | Nimetus | Tähendus ja kirjeldus |
| :---: | :--- | :--- |
| `0` | **Õnnestus (`EXIT_OK`)** | Käsk täideti edukalt ilma vigadeta. |
| `1` | **Kasutusviga / Valideerimine (`EXIT_USAGE`)** | Rakenduse taseme valideerimisviga (`UsageError`, nt vastastikku välistavate lippude `--browser` ja `--api-key` korraga määramine). |
| `2` | **Autentimisviga / Parser (`EXIT_AUTH`)** | Puuduvad volitused, aegunud võti või ebapiisavad õigused. Click/Typer parseri süntaksivead ja vigased parameetriväärtused (tundmatud valikud, valed väärtused või puuduvad kohustuslikud argumendid) tagastavad samuti koodi 2. |
| `3` | **Serveri või võrgu viga (`EXIT_SERVER`)** | Omi serveri HTTP 5xx vastus või võrguühenduse katkestus. |
| `4` | **Päringulimiidi ületamine (`EXIT_RATE_LIMITED`)** | HTTP 429 vastus — liiga palju päringuid lühikese aja jooksul. |
| `5` | **Ressurssi ei leitud (`EXIT_NOT_FOUND`)** | HTTP 404 vastus — otsitud objekti ei eksisteeri. |

---

## 6. Skriptimise näited erinevates terminalikeskkondades

### Bash / Zsh (Linux ja macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Edukalt hangitud $(jq 'length' /tmp/memories.json) mälestust."
else
    code=$?
    echo "Viga mälestuste hankimisel (väljumiskood: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Käsk ebaõnnestus väljumiskoodiga $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Andmed edukalt salvestatud."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Tekkis viga koodiga %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Toiming lõpetati edukalt.
```

---

## 7. Profiilide haldamine ja testimiskeskkond (Staging)

Lipp `--profile` võimaldab paralleelselt hallata mitut konfiguratsiooni (nt isiklik, töö- või testprofiil). Testimiskeskkonna jaoks seadistage profiilile püsiv baasaadress:

```bash
# Püsiva baasaadressi määramine staging profiilile
omi --profile staging config set api_base https://api.staging.omi.me

# Sisselogimine testkeskkonna (staging) profiili
omi --profile staging auth login --api-key omi_dev_staging_voti

# Käskude käivitamine testprofiilis (suunatud püsivalt testkeskkonda)
omi --profile staging memory list

# Alternatiivselt ühekordne baasaadressi ülekirjutamine konkreetse käsu jaoks:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Oluline märkus `--api-base` kohta:** Lipp `--api-base` toimib ainult ajutise ülekirjutusena konkreetse käsu jaoks ega salvestu automaatselt profiili konfiguratsiooni. Püsivaks kasutamiseks määrake see käsuga `config set api_base <url>`.

---

## 8. Integratsioon kohaliku töölaua API-ga (Local Desktop API)

Kui Omi töölauarakendus töötab samas arvutis, saate suhelda otse kohaliku serveriga ilma andmeid pilve saatmata. Enne käsu `omi local status` või otsingute käivitamist määrake kindlasti serveri aadress ja pääsuluba:

```bash
# 1. Kohaliku aadressi (vaikimisi port 47778) ja pääsuloa määramine:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="teie_kohalik_lubataht"

# Alternatiivselt püsiv salvestamine profiili:
# omi local configure --url http://127.0.0.1:47778 --token "teie_kohalik_lubataht"

# 2. Kohaliku teenuse oleku kontrollimine (eeldab eelnevalt seadistatud parameetreid)
omi local status

# 3. Ekraanitegevuste otsing päringu ja rakenduse järgi
omi local search-screen "projekti arutelu" --days 1 --app "Slack"
```

---

## 9. Turvalisus ja parimad praktikad

1. **Lipu `--json` paigutus:** Määrake alati enne alamkäsku (`omi --json memory list`).
2. **Väljumiskoodide käsitlemine:** Automatiseerimisskriptides töödelge alati väljumiskoode vahemikus 1 kuni 5.
3. **Pääsuvõtmete turvalisus:** Ärge kunagi avaldage API võtmeid avalikes repositooriumides. Toodangukeskkonnas ja CI/CD süsteemides kasutage keskkonnamuutujat `OMI_API_KEY`.
