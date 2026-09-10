# omi-cli Snabbstartsguide (Swedish Quickstart)

> En praktisk guide för att interagera med Omi direkt från terminalen — utformad för utvecklare och autonoma AI-agenter.

`omi-cli` är det officiella kommandoradsgränssnittet för utvecklar-API:et till [Omi](https://omi.me). Det ger strukturerad och automatiserbar åtkomst till systemets fyra kärnresurser: minnen (memories), konversationer (conversations), åtgärdspunkter (action items) och mål (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Officiell dokumentation:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Källkod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installation

Installation via `pipx` rekommenderas för att köra CLI:t i en isolerad miljö och undvika konflikter med systemberoenden.

```bash
# Rekommenderat: isolerad miljö med pipx
pipx install omi-cli

# Eller standardinstallation med pip
pip install omi-cli
```

> **Observera: Paketnamn vs. Kommandonamn**
> * Paketnamnet på PyPI är **`omi-cli`** (`omi` är ett orelaterat paket).
> * Kommandot i terminalen är helt enkelt **`omi`**.

Verifiera installationen:

```bash
omi --version
omi --help
```

---

## 2. Autentisering (Authentication)

`omi-cli` stöder två primära autentiseringsmetoder:

| Metod | Användningsområde | Kommando |
| :--- | :--- | :--- |
| **API-nyckel för utvecklare (`omi_dev_*`)** | Automatisering, CI/CD, headless-servrar, AI-agenter | `omi auth login --api-key` eller miljövariabeln `OMI_API_KEY` |
| **Webbläsare OAuth (Google/Apple)** | Lokala utvecklingsmaskiner och skrivbord | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktiv inloggning
Kör kommandot utan flaggor för att välja metod:

```bash
omi auth login
# 1) Browser — webbläsarinloggning (standard Google; för Apple använd `--provider apple`)
# 2) API key — mata in utvecklarnyckel från app.omi.me
```

### Direkt webbläsarinloggning
```bash
# Standardinloggning via Google
omi auth login --browser

# Inloggning via Apple-konto
omi auth login --browser --provider apple
```

### Autentisering med API-nyckel
Skapa en nyckel på [app.omi.me](https://app.omi.me) under **Developer → API Keys**:

```bash
# Spara i den lokala profilen via kommandot
omi auth login --api-key omi_dev_...

# Eller ange som miljövariabel (perfekt för containers och CI/CD)
# Obs: om den aktiva profilen redan har en sparad nyckel, kör `omi auth logout` först.
export OMI_API_KEY="omi_dev_din_hemliga_nyckel"
```

### Verifiera sessionen
* `omi auth status`: visar aktiv profil och maskerade uppgifter. Utgångsdatum visas endast för OAuth-profiler (fungerar offline).
* `omi auth whoami`: skickar en live-förfrågan till Omi-servern för att verifiera giltighet (kräver nätverksåtkomst).

```bash
omi auth status
omi auth whoami
```

Avsluta sessionen:
```bash
omi auth logout
# Om OMI_API_KEY satts som miljövariabel, ta bort den i sessionen (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Kärnkommandon

### Minnen (Memories)
Strukturerade kontextuella informationsenheter sparade av Omi:

```bash
# Lista sparade minnen
omi memory list

# Skapa ett nytt minne (text som positionellt argument)
omi memory create "Föredrar koncisa tekniska svar med Python-exempel" --category work

# Hämta detaljer om ett specifikt minne
omi memory get <MINNES_ID>
```

### Konversationer (Conversations)
Ljudhistorik och transkriptioner registrerade av Omi-enheter:

```bash
# Lista de 5 senaste konversationerna
omi conversation list --limit 5

# Visa detaljer och fullständig transkription
omi conversation get <KONVERSATIONS_ID> --include-transcript

# Exportera fullständig transkription till JSON-fil
omi --json conversation get <KONVERSATIONS_ID> --include-transcript > transkription.json
```

### Åtgärdspunkter (Action Items)
Uppgifter och att-göra-punkter extraherade automatiskt från samtal:

```bash
# Lista öppna uppgifter
omi action-item list --open

# Markera en uppgift som slutförd
omi action-item complete <UPPGIFTS_ID>
```

### Mål (Goals)
Framstegsspårning och långsiktiga mål:

```bash
# Lista aktiva mål
omi goal list

# Skapa ett nytt kvantitativt mål (titel som positionellt argument)
omi goal create "Drick 2 liter vatten per dag" --type numeric --target 2 --unit liters
```

---

## 4. Automatisering och JSON-utdata (`--json`)

`omi-cli` är optimerat för automatiserade rörledningar och Unix-verktyg som `jq`. Den globala flaggan `--json` ger ren, strukturerad utdata:

```bash
# Hämta minnen i JSON-format och filtrera fält med jq
omi --json memory list | jq '.[] | {id, content, category}'

# Extrahera titlar på senaste konversationer
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Granska rådata för öppna åtgärdspunkter
omi --json action-item list --open | jq '.'
```

> **Viktig syntaxregel:**
> Flaggan `--json` är ett **globalt alternativ** och måste alltid placeras **före** underkommandot:
> * Korrekt: `omi --json memory list`
> * Felaktigt: `omi memory list --json`

---

## 5. Slutkoder (Exit Codes)

Standardiserade slutkoder för tillförlitlig felhantering i skalskript och automatiseringsflöden:

| Slutkod | Betydelse | Beskrivning |
| :---: | :--- | :--- |
| `0` | **Lyckades (Success)** | Kommandot utfördes felfritt. |
| `1` | **Valideringsfel** | Felaktiga datavärden eller applikationsvalideringsfel; Click-parser syntaxfel returnerar kod `2`. |
| `2` | **Autentiseringsfel / Click-syntaxfel** | Ingen aktiv session, utgånget token eller ogiltig kommandosyntax. |
| `3` | **Serverfel / Nätverksfel** | HTTP 5xx-svar, anslutningstimeout eller servern kunde inte nås. |
| `4` | **Hastighetsbegränsning (Rate Limit)** | HTTP 429 Too Many Requests — vänta innan nytt försök. |
| `5` | **Hittades inte (Not Found)** | HTTP 404 Not Found — den efterfrågade resursen finns inte. |

---

## 6. Exempel på skalskript

### Bash / Zsh (Linux / macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

# Verifiera sessionen via whoami (returnerar kod != 0 vid obehörighet)
if ! omi auth whoami > /dev/null 2>&1; then
    echo "Fel: Autentisering krävs. Kör 'omi auth login'." >&2
    exit 2
fi

# Hämta öppna uppgifter och bearbeta JSON
open_items=$(omi --json action-item list --open)
echo "Hittade uppgifter: $(echo "$open_items" | jq 'length')"
```

### PowerShell (Windows)
```powershell
# Sätt miljövariabel för sessionen
$env:OMI_API_KEY = "omi_dev_din_hemliga_nyckel"

# Hämta minnen och konvertera direkt till PowerShell-objekt
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Kontrollera slutkod
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi-kommandot misslyckades med felkod $LASTEXITCODE."
}
```

---

## 7. Lokal Desktop API-integration

När Omi Desktop körs lokalt kan CLI:t kommunicera direkt utan molnanrop:

```bash
# Konfigurera lokal slutpunkt och token
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Kontrollera lokal anslutningsstatus
omi --json local status

# Sök efter sparad text på skärmen
omi --json local search-screen "kvartalsrapport" --days 7 --app Safari
```

---

## 8. Profilhantering (Profiles)

Alternativet `--profile` tillåter separation av personliga konton, arbetskonton och testmiljöer. Konfigurationen sparas i `~/.omi/config.toml`:

```bash
# Inloggning till personlig profil
omi --profile personal auth login

# Inloggning till arbetsprofil
omi --profile work auth login

# Kör kommando under specifik profil
omi --profile work memory list
```

---

## 9. Säkerhetsrekommendationer

* **Checka aldrig in nycklar i Git:** Använd hemlighetshanterare, miljövariabler eller `.env`-filer som uteslutits i `.gitignore`.
* **Skydda terminalhistorik:** Undvik att skicka nycklar direkt som kommandoradsflaggor på delade system.
* **Katalogbehörigheter:** På Unix-system, se till att konfigurationsmappen har strikta behörigheter (`chmod 700 ~/.omi`).
