# Rychlý průvodce omi-cli (Czech Quickstart)

> Praktický průvodce pro práci s Omi přímo z příkazové řádky — navrženo pro vývojáře a autonomní AI agenty.

`omi-cli` je oficiální rozhraní příkazové řádky pro vývojářské API platformy [Omi](https://omi.me). Umožňuje strukturovaný a programovatelný přístup ke 4 klíčovým prostředkům ekosystému: vzpomínkám (memories), konverzacím (conversations), úkolům (action items) a cílům (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Oficiální dokumentace:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Zdrojový kód:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalace

Doporučujeme instalaci pomocí nástroje `pipx`, který spouští CLI v izolovaném virtuálním prostředí a zabraňuje konfliktům se systémovými závislostmi.

```bash
# Doporučeno: izolovaná instalace pomocí pipx
pipx install omi-cli

# Případně standardní instalace přes pip
pip install omi-cli
```

> **Důležité upozornění: Název balíčku vs. název příkazu**
> * Název balíčku na PyPI je **`omi-cli`** (balíček `omi` je nesouvisející knihovna).
> * Spustitelný příkaz v terminálu je jednoduše **`omi`**.

Ověření úspěšné instalace:

```bash
omi --version
omi --help
```

---

## 2. Autentizace (Authentication)

`omi-cli` podporuje dvě primární metody ověření identity:

| Metoda | Vhodné využití | Ukázkový příkaz |
| :--- | :--- | :--- |
| **Vývojářský API klíč (`omi_dev_*`)** | Automatizace, CI/CD, servery bez grafického rozhraní, AI agenti | `omi auth login --api-key omi_dev_...` nebo `OMI_API_KEY` |
| **Přihlášení přes prohlížeč (Google/Apple)** | Lokální pracovní stanice vývojářů | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktivní přihlášení
Spuštění příkazu bez parametrů otevře interaktivní nabídku:

```bash
omi auth login
# 1) Browser — přihlášení přes webový prohlížeč (výchozí Google; pro Apple použijte `--provider apple`)
# 2) API key — interaktivní zadání vývojářského klíče z app.omi.me
```

### Přímé přihlášení přes prohlížeč
```bash
# Výchozí přihlášení přes Google účet
omi auth login --browser

# Přihlášení přes Apple účet
omi auth login --browser --provider apple
```

### Autentizace pomocí API klíče
Vygenerujte klíč na [app.omi.me](https://app.omi.me) v sekci **Developer → API Keys**:

```bash
# Uložení do lokálního profilu přes příkazovou řádku
omi auth login --api-key omi_dev_...

# Nebo nastavení proměnné prostředí (ideální pro kontejnery a CI/CD)
# Poznámka: Pokud má aktivní profil již uložený klíč, nejprve spusťte `omi auth logout`.
export OMI_API_KEY="omi_dev_vas_tajny_klic_zde"
```

### Kontrola stavu autentizace
* `omi auth status`: Zobrazí aktivní lokální profil a maskované pověření; datum vypršení platnosti se zobrazuje pouze u OAuth profilů (funguje offline).
* `omi auth whoami`: Odešle ověřovací dotaz na server Omi pro potvrzení platnosti pověření v reálném čase (vyžaduje síťové připojení).

```bash
omi auth status
omi auth whoami
```

Ukončení relace:
```bash
omi auth logout
# Pokud byla nastavena proměnná OMI_API_KEY, zrušte ji v relaci (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Základní příkazy

### Vzpomínky (Memories)
Syntetizované atomické kontextové informace uložené platformou Omi:

```bash
# Výpis uložených vzpomínek
omi memory list

# Vytvoření nové vzpomínky (text jako poziční argument)
omi memory create "Preferuje stručné technické odpovědi s příklady v Pythonu" --category work

# Zobrazení detailu konkrétní vzpomínky
omi memory get <ID_VZPOMINKY>
```

### Konverzace (Conversations)
Zvukové záznamy a textové přepisy zachycené zařízeními Omi:

```bash
# Výpis 5 nejnovějších konverzací
omi conversation list --limit 5

# Zobrazení podrobností a úplného textového přepisu
omi conversation get <ID_KONVERZACE> --include-transcript

# Export úplného přepisu do souboru JSON
omi --json conversation get <ID_KONVERZACE> --include-transcript > prepis.json
```

### Úkoly (Action Items)
Akční položky a úkoly automaticky vygenerované z dialogů:

```bash
# Výpis otevřených úkolů
omi action-item list --open

# Označení úkolu jako splněného
omi action-item complete <ID_UKOLU>
```

### Cíle (Goals)
Sledování pokroku a dlouhodobých metrik:

```bash
# Výpis aktivních cílů
omi goal list

# Vytvoření nového kvantitativního cíle (název jako poziční argument)
omi goal create "Vypít 2 litry vody denně" --type numeric --target 2 --unit liters
```

---

## 4. Automatizace a výstup v JSON (`--json`)

Rozhraní `omi-cli` je optimalizováno pro skriptování a integraci s nástroji jako `jq`. Globální přepínač `--json` zajistí čistý formátovaný výstup:

```bash
# Výpis vzpomínek v JSON a extrakce polí pomocí jq
omi --json memory list | jq '.[] | {id, content, category}'

# Získání názvů posledních konverzací
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Zobrazení nezpracovaných dat otevřených úkolů
omi --json action-item list --open | jq '.'
```

> **Důležité pravidlo syntaxe:**
> Přepínač `--json` je **globální volba** a musí být umístěn **před** dílčím příkazem:
> * Správně: `omi --json memory list`
> * Nesprávně: `omi memory list --json`

---

## 5. Návratové kódy (Exit Codes)

Standardizované návratové kódy pro spolehlivé ošetření chyb v shellových skriptech:

| Kód | Význam | Popis |
| :---: | :--- | :--- |
| `0` | **Úspěch (Success)** | Příkaz byl úspěšně vykonán. |
| `1` | **Chyba validace (Usage Error)** | Neplatné hodnoty parametrů nebo aplikační chyba validace; syntaktická chyba parseru Click vrací kód `2`. |
| `2` | **Chyba autentizace / syntaxe Click** | Neplatné nebo chybějící přihlášení, vypršený token nebo neplatná syntaxe příkazu Click. |
| `3` | **Chyba serveru / sítě** | Odpověď HTTP 5xx, vypršení časového limitu připojení nebo nedostupný server. |
| `4` | **Omezení četnosti dotazů (Rate Limit)** | HTTP 429 Too Many Requests — před opakováním je nutné počkat. |
| `5` | **Nenalezeno (Not Found)** | HTTP 404 Not Found — požadovaný prostředek neexistuje. |

---

## 6. Příklady skriptů pro shell

### Bash / Zsh (Linux / macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

# Ověření relace pomocí whoami (vrací kód != 0 při neplatném přihlášení)
if ! omi auth whoami > /dev/null 2>&1; then
    echo "Chyba: Je vyžadováno přihlášení. Spusťte 'omi auth login'." >&2
    exit 2
fi

# Získání otevřených úkolů a zpracování v JSON
open_items=$(omi --json action-item list --open)
echo "Počet otevřených úkolů: $(echo "$open_items" | jq 'length')"
```

### PowerShell (Windows)
```powershell
# Nastavení proměnné prostředí pro relaci
$env:OMI_API_KEY = "omi_dev_vas_tajny_klic_zde"

# Načtení dat a přímá konverze JSON na objekt PowerShellu
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Kontrola návratového kódu
if ($LASTEXITCODE -ne 0) {
    Write-Error "Příkaz Omi selhal s chybovým kódem $LASTEXITCODE."
}
```

---

## 7. Integrace s lokálním Desktop API

Pokud na počítači běží aplikace Omi Desktop, může CLI komunikovat přímo s ní bez volání cloudu:

```bash
# Konfigurace lokálního koncového bodu a tokenu
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Kontrola stavu lokálního připojení
omi --json local status

# Vyhledávání v textu zachyceném na obrazovce
omi --json local search-screen "čtvrtletní zpráva" --days 7 --app Safari
```

---

## 8. Správa více profilů (Profiles)

Přepínač `--profile` umožňuje oddělit osobní, pracovní nebo testovací účty. Nastavení se ukládá do `~/.omi/config.toml`:

```bash
# Přihlášení do osobního profilu
omi --profile personal auth login

# Přihlášení do pracovního profilu
omi --profile work auth login

# Spuštění příkazu v kontextu vybraného profilu
omi --profile work memory list
```

---

## 9. Doporučené bezpečnostní postupy

* **Nikdy neukládejte klíče do Gitu:** Vždy používejte správce hesel, proměnné prostředí nebo soubory `.env` uvedené v `.gitignore`.
* **Chraňte historii terminálu:** Na sdílených počítačích nepředávejte klíč jako argument příkazu, ale využijte proměnnou `OMI_API_KEY`.
* **Oprávnění k adresáři:** V systémech Unix zabezpečte konfigurační složku striktními přístupovými právy (`chmod 700 ~/.omi`).
