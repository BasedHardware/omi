# Snabbstartsguide för omi-cli (Swedish Quickstart)

Praktisk referensguide för det officiella kommandoradsgränssnittet för Omi (`omi-cli`).
Detta dokument beskriver installation, autentisering, datahanteringskommandon och automatiseringstekniker för skript och autonoma AI-agenter.

---

## Översikt och Körbar Fil

* **PyPI-paketnamn:** `omi-cli`
* **Körbart kommando:** `omi`

För att undvika förväxling vid installation och körning:

```bash
# Installeras med paketnamnet:
pipx install omi-cli

# Körs med det kortare kommandot:
omi --help
```

---

## Installation

Användning av `pipx` rekommenderas för att köra CLI-verktyget i en isolerad virtuell miljö och undvika beroendekonflikter.

### Rekommenderad Metod (`pipx`)

```bash
pipx install omi-cli
```

Uppgradera till den senaste versionen:

```bash
pipx upgrade omi-cli
```

### Alternativ Metod (`pip`)

```bash
pip install --user omi-cli
```

Verifiera att installationen fungerar:

```bash
omi --version
```

---

## Autentisering

CLI stöder tre primära metoder för autentisering: webbläsarinloggning, utvecklar-API-nyckel och miljövariabel.

### 1. Inloggning via Webbläsare (OAuth)

Google används som standard. Om du föredrar Apple-konto anger du `--provider apple`.

```bash
# Inloggning via Google (standard)
omi auth login --browser

# Inloggning via Apple
omi auth login --browser --provider apple
```

### 2. Inloggning med API-nyckel (Headless / CI/CD)

Lämpligt för fjärrservrar, SSH-sessioner och automatiserade distributionsrör:

```bash
omi auth login --api-key
```

Klistra in din utvecklarnyckel som genererats på [app.omi.me](https://app.omi.me) under **Developer → API Keys**.

### 3. Miljövariabel

För Docker-containrar och automatiserade miljöer utan fillagring:

```bash
export OMI_API_KEY="omi_dev_din_hemliga_nyckel"
```

> **Obs:** Om din aktiva profil redan har en sparad nyckel, kör först `omi auth logout` så att miljövariabeln ges företräde.

### Kontrollera Autentiseringsstatus

* **Offline-kontroll:**
  `omi auth status` visar aktiv profil och maskerad nyckel. Utgångsdatum visas endast för OAuth-profiler.
* **Online-kontroll:**
  `omi auth whoami` skickar en verifieringsförfrågan till Omi-servern för att bekräfta giltigheten i realtid.

```bash
omi auth status
omi auth whoami
```

Avsluta sessionen:

```bash
omi auth logout
# Om OMI_API_KEY är satt i miljön, ta även bort den (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## Primära Arbetsflöden

### Minnen (`omi memory`)

Minnen representerar atomära kontextelement som sparats av Omi.

```bash
# Lista de senaste minnena
omi memory list --limit 10

# Skapa ett nytt minne manuellt
omi memory create --text "Projektmöte bokat till tisdag kl. 10:00 med det tekniska teamet."

# Semantisk sökning bland minnen
omi memory search "projektmöte"
```

### Konversationer (`omi conversation`)

Hantering av inspelade samtal och ljudtranskriptioner.

```bash
# Lista konversationer
omi conversation list --limit 5

# Hämta information om en specifik konversation
omi conversation get conv_123456

# Exportera fullständig transkription i Markdown-format
omi conversation export conv_123456 --format markdown > transkription.md
```

### Åtgärdspunkter och Uppgifter (`omi action-item`)

Uppgifter som extraherats automatiskt ur konversationer.

```bash
# Lista väntande uppgifter
omi action-item list --status pending

# Markera en uppgift som slutförd
omi action-item update act_789012 --completed
```

### Mål (`omi goal`)

Hantering av personliga och professionella mål.

```bash
# Visa aktiva mål
omi goal list

# Skapa ett nytt mål
omi goal create --title "Slutföra flerspråkig dokumentation" --horizon month

# Uppdatera målets framsteg
omi goal update goal_345678 --progress 75
```

---

## Strukturerad Automatisering (`--json` & `jq`)

Alla `omi`-kommandon accepterar den globala flaggan `--json`, vilket möjliggör maskinläsbarhet för skript och datapipeliner.

### Filtrera och Extrahera med `jq`

```bash
# Extrahera all text från minnen
omi --json memory list --limit 20 | jq -r '.[].content'

# Filtrera oavslutade uppgifter
omi --json action-item list | jq '.[] | select(.completed == false) | {id: .id, description: .description}'
```

---

## Tabell över Slutkoder (Exit Codes)

| Kod | Betydelse | Typisk Orsak |
| :---: | :--- | :--- |
| `0` | **Framgång (Success)** | Åtgärden slutfördes utan fel. |
| `1` | **Applikations- / Valideringsfel** | Ogiltiga datavärden eller misslyckad affärslogik; syntaxfel från Click-parsern returnerar kod `2`. |
| `2` | **Autentiserings- / CLI-syntaxfel** | Saknad inloggning, ogiltig API-nyckel eller ogiltiga kommandoradsflaggor från Click-parsern. |
| `3` | **Server- / Nätverksfel** | HTTP 5xx-svar, tidsgräns överskriden eller servern kan inte nås. |
| `4` | **Hastighetsbegränsad (Rate Limited)** | HTTP 429 Too Many Requests — fördröjd återförsökslogik krävs. |
| `5` | **Hittades Inte (Not Found)** | HTTP 404 Not Found — den begärda resursen existerar inte. |

---

## Plattformsoberoende Skript

### Bash / Zsh (Linux & macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Kontrollerar Omi-autentisering..."
if ! omi auth status > /dev/null 2>&1; then
    echo "Fel: Autentisering krävs. Kör 'omi auth login'." >&2
    exit 2
fi

echo "Skapar ny anteckning..."
omi memory create --text "Automatisk systemkontroll genomförd utan anmärkning."
```

### PowerShell (Windows)

```powershell
Write-Host "Kontrollerar Omi-autentisering..."
omi auth status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Autentisering saknas. Kör 'omi auth login'."
    exit $LASTEXITCODE
}

Write-Host "Hämtar mål..."
omi --json goal list | ConvertFrom-Json | ForEach-Object {
    [PSCustomObject]@{
        Id = $_.id
        Titel = $_.title
        Framsteg = "$($_.progress)%"
    }
}
```

---

## Lokal Omi Desktop API-integration

När Omi Desktop körs lokalt kan CLI interagera direkt med dess lokala kontexttjänster:

```bash
# Konfigurera lokal skrivbordsport
omi local configure --port 8000

# Sök efter text på den lokalt sparade skärmen
omi local search-screen "kvartalsrapport"
```

---

## Hantering av Flera Profiler

Hantera separata profiler (t.ex. privat, arbete och test) med `--profile` eller via `~/.omi/config.toml`:

```bash
# Använd en specifik profil
omi --profile arbete memory list

# Använd en testprofil med anpassad API-slutpunkt
omi --profile staging --api-url https://api-staging.omi.me memory list
```

---

## Säkerhet och Bästa Praxis

1. **Nyckelhemlighet:** Spara aldrig API-nycklar eller sessionsuppgifter i publika Git-arkiv.
2. **Skalsäkerhet:** Undvik att skicka nycklar direkt som kommandoradsargument på delade datorer; föredra interaktiv inmatning eller miljövariabeln `OMI_API_KEY`.
3. **Filbehörigheter:** På Unix-system rekommenderas att begränsa rättigheterna för katalogen `~/.omi/` (`chmod 700 ~/.omi`).
