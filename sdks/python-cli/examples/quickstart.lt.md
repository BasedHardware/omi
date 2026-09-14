# Greito pradžios vadovas omi-cli (Lithuanian Quickstart)

`omi-cli` yra oficiali komandinės eilutės sąsaja (CLI), skirta [Omi](https://www.omi.me) platformai ir Omi Developer API. Ji leidžia saugiai valdyti prisiminimus (memories), pokalbius (conversations), veiksmų elementus (action items) ir tikslus (goals) tiesiogiai iš terminalo, automatizavimo scenarijų ar AI agentų.

---

## 1. Diegimas

Paketas yra platinamas PyPI platformoje pavadinimu **`omi-cli`**, o jūsų sistemoje įdiegta vykdomoji komanda yra **`omi`**:

```bash
# Rekomenduojamas izoliuotas diegimas per pipx:
pipx install omi-cli

# Arba įprastas diegimas per pip:
pip install omi-cli
```

Patikrinkite diegimo sėkmingumą ir pasiekiamą versiją:

```bash
omi --version
omi --help
```

---

## 2. Autentifikavimas

`omi-cli` palaiko prisijungimą per naršyklę (OAuth) arba naudojant kūrėjo API raktą (`omi_dev_*`).

### Parinktis A: Prisijungimas per naršyklę (rekomenduojama vartotojams)

Paleiskite interaktyvų prisijungimą per numatytąjį Google teikėją arba Apple ID:

```bash
# Numatytasis prisijungimas (Google OAuth)
omi auth login --browser

# Prisijungimas per Apple ID
omi auth login --browser --provider apple
```

### Parinktis B: Prisijungimas su API raktu (tinkama serveriams ir CI/CD)

Kūrėjo API raktą galite sugeneruoti Omi portale skiltyje **Developer → API Keys**. Visi raktai prasideda prefiksu `omi_dev_`.

```bash
# Rakto išsaugojimas vietiniame profilyje
omi auth login --api-key omi_dev_jusu_raktas_cia

# Arba aplinkos kintamojo nustatymas (idealu konteineriams ir automatizavimui):
export OMI_API_KEY="omi_dev_jusu_raktas_cia"
```

### Autentifikavimo būsenos patikra

* `omi auth status`: Rodo aktyvų profilį ir paslėptą identifikatorių be tinklo užklausų (veikia neprisijungus).
* `omi auth whoami`: Siunčia patvirtintą užklausą į Omi serverį ir patvirtina sesijos galiojimą (reikalingas interneto ryšys).

```bash
omi auth status
omi auth whoami
```

### Atsijungimas (Logout)

Norėdami pašalinti vietoje saugomus prisijungimo duomenis:

```bash
omi auth logout
# Jei naudojote OMI_API_KEY aplinkos kintamąjį, pašalinkite jį iš sesijos:
unset OMI_API_KEY
```

> **Saugumo pastaba:** Konfigūracijos failas saugomas `~/.omi/config.toml`. Rekomenduojama apriboti teises: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Pagrindinės komandos

### Prisiminimai (Memories)

Kontekstinės pastabos ir įžvalgos, kurias užfiksavo Omi:

```bash
# Išsaugoti prisiminimai
omi memory list

# Naujo prisiminimo sukūrimas
omi memory create "Vartotojas pageidauja glaustų techninių atsakymų su Python pavyzdžiais" --category work

# Konkretaus prisiminimo gavimas pagal identifikatorių
omi memory get <MEMORY_ID>
```

### Pokalbiai (Conversations)

Užfiksuotų pokalbių įrašai ir garso transkripcijos:

```bash
# Naujausi pokalbiai
omi conversation list

# Pokalbiai su pilna transkripcija (transcript)
omi conversation list --include-transcript

# Konkretaus pokalbio peržiūra
omi conversation get <CONVERSATION_ID>
```

### Veiksmų elementai (Action Items)

Iš pokalbių išskirti darbai ir užduotys:

```bash
# Visi veiksmų elementai
omi action-item list

# Tik atidarytos (nebaigtos) užduotys
omi action-item list --open

# Užduoties pažymėjimas atlikta
omi action-item complete <ACTION_ITEM_ID>
```

### Tikslai (Goals)

Asmeninių ar profesinių tikslų stebėjimas:

```bash
# Tikslų sąrašas
omi goal list

# Naujo skaitinio tikslo sukūrimas (pavadinimas pateikiamas kaip pozicinis argumentas)
omi goal create "Dienos vandens norma" --type numeric --target 2500 --unit "ml"
```

---

## 4. Darbas su JSON formatu ir komandų grandinės

### Visuotinis jungiklis `--json`

Jungiklis `--json` yra globali parinktis ir **visada turi būti nurodoma prieš subkomandą**:

```bash
# Teisingas nurodymas:
omi --json memory list

# Rezultatų filtravimas su jq įrankiu:
omi --json memory list --limit 10 | jq '.[].content'
```

### Puslapiavimas (Pagination)

Didelėms duomenų apimtims naršyti naudokite `--limit` ir `--offset` parametrus:

```bash
# Pirmas puslapis (įrašai 0–24)
omi --json memory list --limit 25 --offset 0 > prisiminimai-1-psl.json

# Antras puslapis (įrašai 25–49)
omi --json memory list --limit 25 --offset 25 > prisiminimai-2-psl.json
```

Išvesties nukreipimas perrašo paskirties failą. Prieš automatizuotą apdorojimą visada patikrinkite komandos išėjimo kodą.

---

## 5. Išėjimo kodai (Exit Codes Contract)

`omi-cli` naudoja griežtą išėjimo kodų sutartį patikimam klaidų apdorojimui scenarijuose ir CI/CD sistemose (pagal `omi_cli/errors.py`):

| Kodas | Pavadinimas | Reikšmė ir aprašymas |
| :---: | :--- | :--- |
| `0` | **Sėkmė (`EXIT_OK`)** | Komanda įvykdyta sėkmingai be klaidų. |
| `1` | **Naudojimo klaida / Validacija (`EXIT_USAGE`)** | Neteisingos argumentų reikšmės arba programos lygio validacijos klaida (pvz., vienu metu nurodžius `--browser` ir `--api-key`). |
| `2` | **Autentifikavimo klaida (`EXIT_AUTH`) / Parser** | Trūksta prisijungimo duomenų, baigėsi rakto galiojimas arba nepakanka teisių. Click sintaksės klaidos (nežinomi parametrai/trūkstami argumentai) taip pat grąžinamos su kodu 2. |
| `3` | **Serverio arba tinklo klaida (`EXIT_SERVER`)** | HTTP 5xx atsakymas iš Omi serverio arba tinklo ryšio sutrikimas. |
| `4` | **Užklausų limito viršijimas (`EXIT_RATE_LIMITED`)** | HTTP 429 atsakymas — per daug užklausų per trumpą laiką. |
| `5` | **Išteklius nerastas (`EXIT_NOT_FOUND`)** | HTTP 404 atsakymas — ieškomas objektas neegzistuoja. |

---

## 6. Pavyzdžiai skirtingoms terminalo aplinkoms

### Bash / Zsh (Linux ir macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Sėkmingai gauta $(jq 'length' /tmp/memories.json) prisiminimų."
else
    code=$?
    echo "Klaida gaunant prisiminimus (exit code: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Komanda nepavyko su kodu $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Duomenys sėkmingai išsaugoti."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Įvyko klaida su kodu %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Operacija atlikta sėkmingai.
```

---

## 7. Profilių valdymas ir testavimo aplinka

Parinktis `--profile` leidžia vienu metu palaikyti kelias konfigūracijas. Testavimo aplinkai (staging) naudokite `--api-base`:

```bash
# Prisijungimas prie testavimo aplinkos (staging) profilio
omi --profile staging --api-base https://api.staging.omi.me auth login --api-key omi_dev_staging_raktas

# Komandos vykdymas staging profilyje
omi --profile staging memory list
```

---

## 8. Integracija su vietine Desktop API sąsaja

Jei veikia Omi darbalaukio programa, galite bendrauti tiesiogiai su vietiniu serveriu nesiųsdami duomenų į debesį. Prieš vykdydami vietines komandas nustatykite mazgo adresą ir prieigos raktą:

```bash
# Vietinio mazgo adreso (numatytasis prievadas 47778) ir rakto nustatymas:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="jusu_vietinis_raktas"

# Vietinio mazgo būsenos patikra
omi local status

# Ekrano aktyvumo paieška pagal užklausą ir programą
omi local search-screen "projekto aptarimas" --days 1 --app "Slack"
```

---

## 9. Geriausios praktikos santrauka

1. **`--json` jungiklio vieta:** Visada nurodykite prieš subkomandą (`omi --json memory list`).
2. **Išėjimo kodų valdymas:** Scenarijuose tikrinkite ir apdorokite išėjimo kodus nuo 1 iki 5.
3. **Prieigos raktų saugumas:** Niekada nekelkite API raktų į viešas saugyklas. Gamybinėje ir CI/CD aplinkoje naudokite kintamąjį `OMI_API_KEY`.
