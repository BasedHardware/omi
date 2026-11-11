# Hasteko Gida Azkarra: omi-cli (Euskara)

`omi-cli` Omi ekosistemarekin elkarreragiteko komando-lerroko interfaze (CLI) ofiziala da: oroitzapenetara (memories), elkarrizketetara (conversations), ekintza-elementuetara (action items) eta helburuetara (goals) sartzeko balio du. Gida hau euskaraz idatzita dago osorik, automatizazio-inguruneetarako, terminal-erabiltzaileentzat eta garatzaileentzat.

---

## 1. Instalazioa (Installation)

Paketea PyPI biltegian `omi-cli` izenarekin banatzen da. Behin instalatuta, `omi` komandoa erabilgarri egongo da zure `$PATH` bidean:

```bash
# Gomendatutako metodoa: ingurune isolatua pipx bidez
pipx install omi-cli

# Edo ohiko pip bidez:
pip install omi-cli
```

Egiaztatu instalazioa bertsioa eta laguntza-mezua kontsultatuz:

```bash
omi --version
omi --help
```

> **Oharra:** PyPI paketearen izena `omi-cli` da (beste pakete batek `omi` izen hutsa duelako), baina terminaleko komandoa `omi` da beti.

---

## 2. Autentifikazioa (Authentication)

`omi-cli` tresnak nabigatzaile bidezko saio-hasiera interaktiboa zein garatzaileen API gakoak onartzen ditu:

```bash
omi auth login
# 1) Browser — Nabigatzaile bidezko saio-hasiera (Google edo Apple)
# 2) API key — app.omi.me paneleko garatzaile-gakoa itsastea
```

### Nabigatzaile bidezko saio-hasiera

```bash
# Saioa hasi Google kontuarekin (lehenetsia)
omi auth login --browser

# Saioa hasi Apple kontuarekin
omi auth login --browser --provider apple
```

### Garatzailearen API gako bidezko saio-hasiera

Sortu API gako bat [app.omi.me](https://app.omi.me) aginte-panelean **Developer → API Keys** atalean:

```bash
# Gakoa uneko profil aktiboan gordetzea
omi auth login --api-key omi_dev_zure_gakoa_hemen

# Edo ingurune-aldagai gisa ezartzea (Docker eta CI/CD prozesuetarako gomendatua):
export OMI_API_KEY="omi_dev_zure_gakoa_hemen"
```

> **Segurtasun eta lehentasun oharra:**
> * `--api-key` aukera zuzenean komando-lerroan erabiltzeak gakoa terminaleko historian (`shell history`) eta sistemako prozesu-zerrendan agerian uzten du. Makina partekatuetan, erabili modu interaktiboa (`omi auth login`) edo `OMI_API_KEY` ingurune-aldagaia.
> * Profil aktiboak dagoeneko konfigurazioan gako bat gordeta badu, lehentasuna du ingurune-aldagaiaren gainetik. `OMI_API_KEY` erabiltzeko, amaitu saioa aldez aurretik `omi auth logout` bidez edo erabili profil berri bat.

### Saioaren egoera egiaztatzea

* `omi auth status`: Profil aktiboa eta lokalean gordetako identifikatzaile mozorrotua erakusten ditu (lineaz kanpo funtzionatzen du).
* `omi auth whoami`: Sareko eskaera bat bidaltzen du Omi zerbitzarietara saioaren baliozkotasuna egiaztatzeko.

```bash
omi auth status
omi auth whoami
```

### Saioa amaitzea (Logout)

Lokalean gordetako kredentzialak ezabatzeko:

```bash
omi auth logout
# OMI_API_KEY ingurune-aldagaia erabili baduzu, kendu saiotik:
unset OMI_API_KEY
```

> **Fitxategien segurtasun-oharra:** Konfigurazioa `~/.omi/config.toml` fitxategian gordetzen da. Unix/Linux sistemetan, baimenak mugatzea gomendatzen da: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Oinarrizko komandoak

### Oroitzapenak (Memories)

Epe luzeko testuinguru-oharrak, gertaerak eta oharrak gordetzea eta bilatzea:

```bash
# Gordetako oroitzapenen zerrenda
omi memory list

# Oroitzapen berria sortzea
omi memory create "Erabiltzaileak erantzun tekniko zehatzak nahiago ditu Python adibideekin" --category work

# Oroitzapen zehatz bat eskuratzea identifikatzailearen bidez
omi memory get <OROITZAPEN_ID>
```

### Elkarrizketak (Conversations)

Omi gailuetako audio-grabaketak eta testu-transkripzioak:

```bash
# Azken 5 elkarrizketen zerrenda
omi conversation list --limit 5

# Elkarrizketa bat eskuratzea bere transkripzio osoarekin batera
omi conversation get <ELKARRIZKETA_ID> --include-transcript
```

### Ekintza-elementuak eta zereginak (Action Items)

Elkarrizketetan automatikoki hautemandako atazak eta ekintzak:

```bash
# Irekita dauden zereginen zerrenda
omi action-item list --open

# Zeregin bat osatuta bezala markatzea
omi action-item complete <ZEREGIN_ID>
```

### Helburuak (Goals)

Epe luzeko helburuen jarraipena eta aurrerapena:

```bash
# Helburu aktiboen zerrenda
omi goal list

# Helburu kuantitatibo berria sortzea (izenburua posizio-argumentu gisa ematen da)
omi goal create "Eguneroko ur-kontsumoa" --type numeric --target 2500 --unit "ml"
```

---

## 4. Automatizazio egituratua eta JSON irteera (`--json`)

`omi-cli` bereziki pentsatuta dago gidoietan eta AI fluxu automatizatuetan integratzeko. `--json` bandera globalak JSON irteera garbia eskaintzen du, `jq` bezalako tresnekin prozesatzeko ezin hobea:

```bash
# Oroitzapenak JSON formatuan eskuratu eta jq bidez iragazi
omi --json memory list | jq '.[] | {id, content, category}'

# Azken 5 elkarrizketen izenburuak erauzi
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Zeregin irekien zerrenda
omi --json action-item list --open | jq '.'
```

> **Sintaxi-arau nagusia:**
> `--json` aukera globala da eta beti azpikomandoaren **aurretik** jarri behar da:
> * Zuzena: `omi --json memory list`
> * Okerra: `omi memory list --json`

### Orrialdekatzea eta datuak esportatzea

Datu bolumen handiagoekin lan egitean erabili `--limit` eta `--offset` parametroak:

```bash
# Datuak orrialdeka deskargatzea
omi --json memory list --limit 25 --offset 0 > oroitzapenak-orria-1.json
omi --json memory list --limit 25 --offset 25 > oroitzapenak-orria-2.json
```

Fitxategi batera birbideratzeak fitxategi lokala sortzen edo gainidazten du. Egiaztatu beti komandoaren irteera-kodea datuak prozesatu aurretik. Errore-mezuak akats-korronte estandarrera (`stderr`) bideratzen dira, beraz hutsik dagoen fitxategi batek ez du bermatzen daturik ez dagoenik. Esportatutako fitxategiek datu konfidentzialak izan ditzakete — babestu itzazu zure segurtasun-arauen arabera.

---

## 5. Irteera-kodeak (Exit Codes Contract)

`omi-cli` tresnak irteera-kodeen hitzarmen zehatza betetzen du gidoietan eta CI/CD sistemetan erroreak modu fidagarrian kudeatzeko (`omi_cli/errors.py` fitxategiarekin bat etorriz):

| Kodea | Izena | Esanahia eta deskribapena |
| :---: | :--- | :--- |
| `0` | **Arrakasta (`EXIT_OK`)** | Komandoa behar bezala eta errorerik gabe exekutatu da. |
| `1` | **Erabilera-errorea / Aplikazio-baliozkotzea (`EXIT_USAGE`)** | Aplikazio-mailako baliozkotze-errorea (`UsageError`, adib. `--browser` eta `--api-key` aukera bateraezinak aldi berean zehaztea). |
| `2` | **Autentifikazio-errorea / Analisi-errorea (`EXIT_AUTH`)** | Kredentzialak falta dira, gakoa iraungita dago edo baimen nahikorik ez dago. Click/Typer analizatzailearen errore sintaktikoek eta baliogabeko aukera-balioek (aukera ezezagunak, `--limit` mugatik kanpoko balioak, aukera baliogabeak edo falta diren argumentuak) 2 kodea itzultzen dute halaber. |
| `3` | **Zerbitzari edo sare-errorea (`EXIT_SERVER`)** | Omi zerbitzariaren HTTP 5xx errore-erantzuna edo sareko konexio-etenaldia. |
| `4` | **Eskaera-muga gaindituta (`EXIT_RATE_LIMITED`)** | HTTP 429 erantzuna — denbora tarte laburrean eskaera gehiegi bidali dira. |
| `5` | **Baliabidea ez da aurkitu (`EXIT_NOT_FOUND`)** | HTTP 404 erantzuna — eskatutako baliabidea ez da existitzen. |

---

## 6. Adibideak terminal-ingurune desberdinetarako

### Bash / Zsh (Linux eta macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Behar bezala eskuratu dira $(jq 'length' /tmp/memories.json) oroitzapen."
else
    code=$?
    echo "Errorea oroitzapenak eskuratzean (irteera-kodea: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Komandoak huts egin du $LASTEXITCODE irteera-kodearekin"
    exit $LASTEXITCODE
}
Write-Host "Datuak ondo gorde dira."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Errorea gertatu da %ERRORLEVEL% irteera-kodearekin
    exit /b %ERRORLEVEL%
)
echo Eragiketa behar bezala burutu da.
```

---

## 7. Profilen kudeaketa eta proba-ingurunea (Staging)

`--profile` aukerak konfigurazio independente batzuk mantentzea ahalbidetzen du (adib. pertsonala, lana edo probak). Proba-inguruneetarako (staging), oinarrizko URLa behin betiko ezar dezakezu profilean:

```bash
# Oinarrizko URLa behin betiko ezartzea staging profilarentzat
omi --profile staging config set api_base https://api.staging.omi.me

# Saioa hasi staging proba-profilean
omi --profile staging auth login --api-key omi_dev_staging_gakoa

# Komandoak staging profilean exekutatzea (betiko zuzenduta staging ingurunera)
omi --profile staging memory list

# Edo aldi baterako gainidaztea komando bakar baterako:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Ohar garrantzitsua `--api-base` aukerari buruz:** `--api-base` banderak komando zehatz horrentzako aldi baterako gainidazte gisa soilik funtzionatzen du eta ez da konfigurazioan automatikoki gordetzen. Erabilera iraunkorrerako erabili `config set api_base <url>`.

---

## 8. Mahaigaineko Tokiko APIarekin integrazioa (Local Desktop API)

Omi Desktop aplikazioa ordenagailu berean exekutatzen ari bada, zuzenean komunikatu zaitezke tokiko zerbitzariarekin datuak lainora bidali gabe. `omi local status` edo bilaketak exekutatu aurretik, ziurtatu helbidea eta segurtasun-tokena ezarrita dituzula:

```bash
# 1. Tokiko helbidea (47778 ataka lehenetsia) eta tokena ezartzea:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="zure_token_lokala"

# Edo behin betiko gordetzea profilean:
# omi local configure --url http://127.0.0.1:47778 --token "zure_token_lokala"

# 2. Tokiko zerbitzuaren egoera egiaztatzea (aurrez ezarritako parametroak behar ditu)
omi local status

# 3. Pantailaren historian bilatzea kontsulta eta aplikazioaren arabera
omi local search-screen "asteroko bilera" --days 1 --app "Slack"
```

---

## 9. Segurtasuna eta jardunbide egokiak

1. **`--json` bultzadaren kokapena:** Jarri beti azpikomandoaren aurretik (`omi --json memory list`).
2. **Irteera-kodeak kudeatzea:** Automatizazio-gidoietan egiaztatu eta kudeatu beti 1etik 5era bitarteko kodeak.
3. **Kredentzialen babesa:** Inoiz ez igo API gakorik kode-biltegi publikoetara. Produkzioan eta CI/CD inguruneetan erabili beti `OMI_API_KEY` aldagaia.
