# omi-cli Ātrā darba sākšanas pamācība (Latvian Quickstart)

> Praktisks ceļvedis Omi izmantošanai tieši no termināļa — izstrādāts izstrādātājiem un autonomiem mākslīgā intelekta (AI) aģentiem.

`omi-cli` ir oficiālais komandrindas interfeiss (CLI) [Omi](https://omi.me) izstrādātāju API platformai. Tas nodrošina strukturētu piekļuvi 4 galvenajiem Omi resursiem: atmiņām (*memories*), sarunām (*conversations*), veicamajiem uzdevumiem (*action items*) un mērķiem (*goals*).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Oficiālā dokumentācija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Pirmkods:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalēšana

Lai nodrošinātu izolētu vidi un novērstu Python atkarību konfliktus ar sistēmas pakotnēm, ieteicams izmantot rīku `pipx`:

```bash
# Ieteicamā metode: izolēta instalācija ar pipx
pipx install omi-cli

# Alternatīva instalācija ar pip (piemēram, virtuālajā vidē)
pip install omi-cli
```

> **Svarīgs precizējums: Pakotnes nosaukums salīdzinājumā ar komandas nosaukumu**
> * Oficiālais pakotnes nosaukums PyPI krātuvē ir **`omi-cli`** (pakotne `omi` ir atsevišķs, nesaistīts projekts).
> * Terminālī izpildāmā komanda ir tieši: **`omi`**.

Pārbaudiet instalāciju, izsaucot versijas un palīdzības informāciju:

```bash
omi --version
omi --help
```

---

## 2. Autentifikācija (Authentication)

`omi-cli` atbalsta divus galvenos autentifikācijas veidus:

| Veids | Pielietojums | Komandas piemērs |
| :--- | :--- | :--- |
| **Izstrādātāja API atslēga (`omi_dev_*`)** | Skripti, CI/CD procesi, serveri, AI aģenti | `omi auth login --api-key ...` vai `OMI_API_KEY` |
| **OAuth pieteikšanās pārlūkprogrammā** | Vietējā izstrāde uz personālā datora | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktīvā pieteikšanās

Izsaucot komandu bez papildu parametriem, tiek atvērta interaktīva izvēlne:

```bash
omi auth login
# 1) Browser — Pieteikšanās ar pārlūkprogrammu (Google vai Apple)
# 2) API key — Izstrādātāja API atslēgas ievadīšana no app.omi.me
```

### Pieteikšanās, izmantojot pārlūkprogrammu

```bash
# Standarta pieteikšanās ar Google kontu
omi auth login --browser

# Alternatīva pieteikšanās ar Apple profilu
omi auth login --browser --provider apple
```

### Pieteikšanās ar izstrādātāja API atslēgu

Ģenerējiet API atslēgu vadības panelī [app.omi.me](https://app.omi.me) sadaļā **Developer → API Keys**:

```bash
# Saglabāt atslēgu pašreizējā lokālajā profilā
omi auth login --api-key omi_dev_jusu_atslega_seit

# Vai iestatīt kā vides mainīgo (ieteicams Docker konteineros un CI/CD konveijeros):
export OMI_API_KEY="omi_dev_jusu_atslega_seit"
```

> **Piezīme par prioritāti:** Ja profilā jau ir saglabāta API atslēga, tā ir prioritāra pār vides mainīgo. Lai izmantotu `OMI_API_KEY`, vispirms izrakstieties ar `omi auth logout` vai izmantojiet jaunu profilu.

### Autentifikācijas statusa pārbaude

* `omi auth status`: Parāda aktīvo profilu un maskētu identifikatoru no lokālās konfigurācijas (darbojas bezsaistē).
* `omi auth whoami`: Veic tīkla pieprasījumu uz Omi serveri, lai pārbaudītu sesijas derīgumu.

```bash
omi auth status
omi auth whoami
```

### Izrakstīšanās (Logout)

Lai noņemtu lokāli saglabātās pieteikšanās piekļuves ziņas:

```bash
omi auth logout
# Ja tika izmantots vides mainīgais OMI_API_KEY, noņemiet to no sesijas:
unset OMI_API_KEY
```

> **Drošības piezīme:** Konfigurācija tiek glabāta failā `~/.omi/config.toml`. Unix vidē ieteicams iestatīt ierobežotas piekļuves tiesības: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Pamatkomandas

### Atmiņas (Memories)

Pastāvīgu faktu, novērojumu un konteksta datu fiksēšana:

```bash
# Saglabāto atmiņu saraksts
omi memory list

# Jaunas atmiņas izveide
omi memory create "Lietotājs dod priekšroku kodolīgām atbildēm ar Python piemēriem" --category work

# Konkrētas atmiņas izgūšana pēc identifikatora
omi memory get <ATMINAS_ID>
```

### Sarunas (Conversations)

Audio ieraksti un to teksta transkripcijas no Omi ierīcēm:

```bash
# Pēdējo 5 sarunu saraksts
omi conversation list --limit 5

# Sarunas izgūšana kopā ar pilnu teksta transkripciju
omi conversation get <SARUNAS_ID> --include-transcript
```

### Veicamie uzdevumi (Action Items)

Uzdevumi un rīcības punkti, kas automātiski atpazīti no sarunām:

```bash
# Atvērto uzdevumu saraksts
omi action-item list --open

# Uzdevuma atzīmēšana kā pabeigtam
omi action-item complete <UZDEVUMA_ID>
```

### Mērķi (Goals)

Ilgtermiņa mērķi un to izpildes progresa uzraudzība:

```bash
# Aktīvo mērķu saraksts
omi goal list

# Jauna skaitliska mērķa izveide (nosaukums ir pozicionāls arguments)
omi goal create "Dienas ūdens patēriņš" --type numeric --target 2500 --unit "ml"
```

---

## 4. Strukturēta automatizācija un JSON izvade (`--json`)

`omi-cli` ir viegli integrējams skriptos un AI aģentu darba plūsmās. Globālais karodziņš `--json` nodrošina tīru JSON izvadi, ko var apstrādāt ar rīkiem, piemēram, `jq`:

```bash
# Atmiņu saraksts JSON formātā un filtrēšana ar jq
omi --json memory list | jq '.[] | {id, content, category}'

# Pēdējo 5 sarunu nosaukumu atlase
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Atvērto uzdevumu saraksts
omi --json action-item list --open | jq '.'
```

> **Svarīgs sintakses noteikums:**
> Karodziņš `--json` ir **globāla opcija**, tādēļ tas obligāti jānorāda **pirms** apakškomandas:
> * Pareizi: `omi --json memory list`
> * Nepareizi: `omi memory list --json`

### Lapošana un datu eksportēšana

Darbinot lielus datu apjomus, izmantojiet parametrus `--limit` un `--offset`:

```bash
# Datu iegūšana pa daļām (lapošana)
omi --json memory list --limit 25 --offset 0 > atminas-lapa-1.json
omi --json memory list --limit 25 --offset 25 > atminas-lapa-2.json
```

Pāradresācija uz failu izveido vai aizstāj lokālo failu. Pirms apstrādes vienmēr pārbaudiet komandas iziešanas kodu. Kļūdas tiek rakstītas standarta kļūdu straumē (`stderr`), tāpēc tukšs fails ne vienmēr nozīmē, ka datu nav. Eksportētie faili var saturēt sensitīvu informāciju — glabājiet tos atbilstoši drošības standartiem.

---

## 5. Iziešanas kodi (Exit Codes Contract)

`omi-cli` ievēro stingru iziešanas kodu līgumu, nodrošinot uzticamu kļūdu apstrādi skriptos un CI/CD vidēs (saskaņā ar `omi_cli/errors.py`):

| Kods | Apzīmējums | Nozīme un apraksts |
| :---: | :--- | :--- |
| `0` | **Veiksme (`EXIT_OK`)** | Komanda izpildīta veiksmīgi bez kļūdām. |
| `1` | **Lietošanas kļūda / Validācija (`EXIT_USAGE`)** | Validācijas kļūda lietojumprogrammas līmenī (`UsageError`, piemēram, vienlaicīgi norādot savstarpēji izslēdzošus karodziņus `--browser` un `--api-key`). |
| `2` | **Autentifikācijas kļūda / Parser (`EXIT_AUTH`)** | Trūkst autentifikācijas datu, beidzies atslēgas derīgums vai nepietiekamas tiesības. Click/Typer parsētāja sintakses kļūdas un nederīgas opciju vērtības (nezināmi parametri, kļūdainas vērtības vai trūkstoši argumenti) arī atgriež kodu 2. |
| `3` | **Servera vai tīkla kļūda (`EXIT_SERVER`)** | HTTP 5xx kļūdas atbilde no Omi servera vai tīkla savienojuma pārrāvums. |
| `4` | **Pārsniegts pieprasījumu limits (`EXIT_RATE_LIMITED`)** | HTTP 429 atbilde — par daudz nosūtītu pieprasījumu īsā laika periodā. |
| `5` | **Resurss nav atrasts (`EXIT_NOT_FOUND`)** | HTTP 404 atbilde — pieprasītais objekts neeksistē. |

---

## 6. Skriptēšanas piemēri dažādās termināļa vidēs

### Bash / Zsh (Linux un macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Veiksmīgi iegūtas $(jq 'length' /tmp/memories.json) atmiņas."
else
    code=$?
    echo "Kļūda, iegūstot atmiņas (iziešanas kods: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Komanda neizdevās ar iziešanas kodu $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Dati veiksmīgi saglabāti."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Radās kļūda ar kodu %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Darbība pabeigta veiksmīgi.
```

---

## 7. Profilu pārvaldība un testa vide (Staging)

Parametrs `--profile` ļauj paralēli uzturēt vairākas konfigurācijas (piemēram, personisko, darba vai testa). Testa videi pastāvīgi iestatiet profila bāzes URL:

```bash
# Pastāvīga bāzes URL iestatīšana staging profilam
omi --profile staging config set api_base https://api.staging.omi.me

# Pieteikšanās testa vides (staging) profilā
omi --profile staging auth login --api-key omi_dev_staging_atslega

# Komandu izpilde testa profilā (pastāvīgi novirzīta uz staging vidi)
omi --profile staging memory list

# Alternatīvi — vienreizēja bāzes adreses pārrakstīšana konkrētai komandai:
# omi --profile staging --api-base https://api.staging.omi.me memory list
```

> **Svarīga piezīme par `--api-base`:** Karodziņš `--api-base` darbojas kā pagaidu pārrakstīšana tikai konkrētajai komandai un netiek automātiski saglabāts profila konfigurācijā. Pastāvīgai darbībai iestatiet to ar komandu `config set api_base <url>`.

---

## 8. Integrācija ar vietējo darbvirsmas API (Local Desktop API)

Ja personālajā datorā darbojas Omi darbvirsmas lietotne, varat mijiedarboties tieši ar vietējo serveri, nesūtot datus uz mākoni. Pirms vietējo komandu palaišanas iestatiet adresi un drošības žetonu:

```bash
# 1. Vietējā galapunkta (noklusējuma ports 47778) un piekļuves žetona iestatīšana:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="jusu_vietejais_zeton"

# Alternatīvi — pastāvīga saglabāšana profilā:
# omi local configure --url http://127.0.0.1:47778 --token "jusu_vietejais_zeton"

# 2. Pārbaudīt vietējā pakalpojuma statusu (nepieciešami iepriekš iestatīti parametri)
omi local status

# 3. Ekrāna aktivitāšu meklēšana pēc vaicājuma un lietotnes
omi local search-screen "projekta apspriede" --days 1 --app "Slack"
```

---

## 9. Drošības un labās prakses ieteikumi

1. **Slēdža `--json` pozīcija:** Vienmēr norādiet pirms apakškomandas (`omi --json memory list`).
2. **Iziešanas kodu pārbaude:** Automatizācijas scenārijos vienmēr apstrādājiet atgrieztos kodus no 1 līdz 5.
3. **Piekļuves datu drošība:** Nekad neglabājiet API atslēgas publiskās krātuvēs. Produkcijas un CI/CD vidēs lietojiet vides mainīgo `OMI_API_KEY`.
