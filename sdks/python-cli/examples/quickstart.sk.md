# Rýchly sprievodca omi-cli (Slovak Quickstart)

`omi-cli` je oficiálne rozhranie príkazového riadka (CLI) pre platformu [Omi](https://www.omi.me) a Omi Developer API. Umožňuje bezpečne spravovať spomienky (memories), konverzácie, akčné položky (action items) a ciele priamo z terminálu, skriptov alebo automatizovaných AI agentov.

---

## 1. Inštalácia

Balík je distribuovaný na PyPI pod názvom **`omi-cli`**, pričom nainštalovaný spustiteľný príkaz v systéme je **`omi`**:

```bash
# Odporúčaná izolovaná inštalácia pomocou pipx:
pipx install omi-cli

# Alebo štandardná inštalácia cez pip:
pip install omi-cli
```

Overte úspešnú inštaláciu a dostupnú verziu:

```bash
omi --version
omi --help
```

---

## 2. Autentifikácia

`omi-cli` podporuje prihlásenie cez webový prehliadač (OAuth) alebo pomocou vývojárskeho API kľúča (`omi_dev_*`).

### Možnosť A: Prihlásenie cez prehliadač (odporúčané pre používateľov)

Spustite interaktívne prihlásenie cez predvoleného poskytovateľa (Google) alebo Apple:

```bash
# Predvolené prihlásenie (Google OAuth)
omi auth login --browser

# Prihlásenie cez Apple ID
omi auth login --browser --provider apple
```

### Možnosť B: Prihlásenie pomocou API kľúča (vhodné pre servery a CI/CD)

Vývojársky kľúč získate na portáli Omi v sekcii **Developer → API Keys**. Kľúče začínajú predponou `omi_dev_`.

```bash
# Uloženie kľúča do lokálneho profilu
omi auth login --api-key omi_dev_vas_kluc_tu

# Alebo nastavenie premennej prostredia (ideálne pre kontajnery a automatizáciu):
export OMI_API_KEY="omi_dev_vas_kluc_tu"
```

### Kontrola stavu autentifikácie

* `omi auth status`: Zobrazí aktívny profil a maskovaný identifikátor bez sieťového volania (funguje offline).
* `omi auth whoami`: Odošle overovaciu požiadavku na server Omi a potvrdí platnosť relácie (vyžaduje pripojenie k internetu).

```bash
omi auth status
omi auth whoami
```

### Odhlásenie (Logout)

Pre vymazanie lokálne uložených poverení použite:

```bash
omi auth logout
# Ak používate premennú prostredia OMI_API_KEY, odstráňte ju z relácie:
unset OMI_API_KEY
```

> **Poznámka k bezpečnosti:** Konfiguračný súbor je predvolene uložený v `~/.omi/config.toml`. Odporúča sa nastaviť prístupové práva: `chmod 700 ~/.omi && chmod 600 ~/.omi/config.toml`.

---

## 3. Základné príkazy

### Spomienky (Memories)

Kontextové poznámky a pozorovania zaznamenané zariadením Omi:

```bash
# Zoznam uložených spomienok
omi memory list

# Vytvorenie novej spomienky
omi memory create "Používateľ preferuje technické odpovede a ukážky v jazyku Python" --category work

# Zobrazenie detailu konkrétnej spomienky
omi memory get <MEMORY_ID>
```

### Konverzácie (Conversations)

Záznamy zachytených rozhovorov a prepisy audia:

```bash
# Zoznam posledných konverzácií
omi conversation list

# Zoznam konverzácií vrátane kompletného prepisu (transcript)
omi conversation list --include-transcript

# Zobrazenie detailu konkrétnej konverzácie
omi conversation get <CONVERSATION_ID>
```

### Akčné položky (Action Items)

Úlohy a povinnosti identifikované zo zachytených konverzácií:

```bash
# Zoznam všetkých akčných položiek
omi action-item list

# Zobrazenie iba otvorených (nesplnených) úloh
omi action-item list --open

# Označenie úlohy ako dokončenej
omi action-item complete <ACTION_ITEM_ID>
```

### Ciele (Goals)

Definovanie a sledovanie osobných alebo pracovných cieľov:

```bash
# Zoznam cieľov
omi goal list

# Vytvorenie nového číselného cieľa (názov sa zadáva ako pozičný argument)
omi goal create "Denný príjem vody" --type numeric --target 2500 --unit "ml"
```

---

## 4. Práca s formátom JSON a reťazenie príkazov

### Globálny prepínač `--json`

Prepínač `--json` je globálny prepínač CLI a **musí byť umiestnený pred podpríkazom**:

```bash
# Správne umiestnenie:
omi --json memory list

# Filtrovanie výsledkov pomocou nástroja jq:
omi --json memory list --limit 10 | jq '.[].content'
```

### Stránkovanie (Pagination)

Pre prechádzanie veľkých množstiev dát použite parametre `--limit` a `--offset`:

```bash
# Prvá stránka (položky 0–24)
omi --json memory list --limit 25 --offset 0 > spomienky-strana-1.json

# Druhá stránka (položky 25–49)
omi --json memory list --limit 25 --offset 25 > spomienky-strana-2.json
```

Presmerovanie výstupu prepíše cieľový súbor. Výsledný návratový kód vždy overte pred spracovaním dát v automatizácii.

---

## 5. Návratové kódy (Exit Codes Contract)

`omi-cli` implementuje stabilný kontrakt návratových kódov pre spoľahlivé spracovanie chýb v skriptoch a CI/CD systémoch (pozri `omi_cli/errors.py`):

| Kód | Názov | Popis a význam |
| :---: | :--- | :--- |
| `0` | **Úspech (`EXIT_OK`)** | Príkaz sa vykonal úspešne bez chýb. |
| `1` | **Chyba použitia / Validácia (`EXIT_USAGE`)** | Neplatné hodnoty argumentov alebo zlyhanie aplikačnej validácie (napr. súčasné zadanie `--browser` a `--api-key`). |
| `2` | **Chyba autentifikácie (`EXIT_AUTH`) / Parser** | Chýbajúce prihlasovacie údaje, expirovaný kľúč alebo nedostatočné oprávnenia. Syntaktické chyby Click parsera (neznáme prepínače/chýbajúce argumenty) sú tiež mapované na kód 2. |
| `3` | **Chyba servera alebo siete (`EXIT_SERVER`)** | Odpoveď HTTP 5xx zo servera Omi alebo výpadok sieťového pripojenia. |
| `4` | **Prekročenie limitu požiadaviek (`EXIT_RATE_LIMITED`)** | Odpoveď HTTP 429 — príliš veľa požiadaviek v krátkom čase. |
| `5` | **Zdroj nenájdený (`EXIT_NOT_FOUND`)** | Odpoveď HTTP 404 — požadovaný objekt neexistuje. |

---

## 6. Príklady pre rôzne terminálové prostredia

### Bash / Zsh (Linux a macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

if omi --json memory list --limit 5 > /tmp/memories.json; then
    echo "Úspešne načítaných $(jq 'length' /tmp/memories.json) spomienok."
else
    code=$?
    echo "Chyba pri získavaní spomienok (exit code: $code)" >&2
    exit "$code"
fi
```

### PowerShell (Windows / macOS / Linux)

```powershell
$ErrorActionPreference = "Continue"

omi --json memory list --limit 5 | Out-File -FilePath "$env:TEMP\memories.json" -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    Write-Error "Príkaz zlyhal s kódom $LASTEXITCODE"
    exit $LASTEXITCODE
}
Write-Host "Dáta boli úspešne uložené."
```

### Windows Command Prompt (`cmd.exe`)

```cmd
omi --json memory list --limit 5 > "%TEMP%\memories.json"
if %ERRORLEVEL% NEQ 0 (
    echo Nastala chyba s kódom %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)
echo Operácia prebehla úspešne.
```

---

## 7. Správa viacerých profilov a testovacie prostredie

Prepínač `--profile` umožňuje udržiavať viacero konfigurácií súčasne. Pre testovacie prostredie (staging) použite prepínač `--api-base`:

```bash
# Prihlásenie do profilu pre testovacie prostredie (staging)
omi --profile staging --api-base https://api.staging.omi.me auth login --api-key omi_dev_staging_kluc

# Vykonanie príkazu v rámci profilu staging
omi --profile staging memory list
```

---

## 8. Integrácia s lokálnym Desktop API

Pokiaľ máte spustenú desktopovú aplikáciu Omi, môžete komunikovať priamo s lokálnym rozhraním bez odosielania požiadaviek na cloud. Pred volaním lokálnych príkazov nastavte adresu uzla a token:

```bash
# Nastavenie lokálneho koncového bodu (predvolený port 47778) a tokenu:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="vas_lokalny_token"

# Kontrola stavu lokálneho desktopového uzla
omi local status

# Prehľadávanie aktivity na obrazovke podľa dotazu a aplikácie
omi local search-screen "diskusia k projektu" --days 1 --app "Slack"
```

---

## 9. Zhrnutie osvedčených postupov (Best Practices)

1. **Umiestnenie prepínača `--json`:** Vždy zadávajte pred podpríkazom (`omi --json memory list`).
2. **Kontrola návratových kódov:** V skriptoch a agentoch vždy ošetrujte návratové kódy 1 až 5.
3. **Bezpečnosť poverení:** Nikdy neukladajte API kľúče do repozitárov. V produkcii a CI/CD používajte premennú `OMI_API_KEY`.
