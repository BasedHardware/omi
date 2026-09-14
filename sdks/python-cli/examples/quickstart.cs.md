# omi-cli — rychlý start v češtině

> Praktický průvodce prací s Omi z terminálu. Hodí se pro člověka i pro AI agenta.

`omi-cli` je oficiální rozhraní příkazové řádky pro vývojářské API [Omi](https://omi.me).
Poskytuje rychlý a skriptovatelný přístup ke čtyřem hlavním entitám Omi:
vzpomínkám, konverzacím, úkolům a cílům.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentace:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Zdrojový kód:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalace

Doporučený způsob je `pipx`: nainstaluje nástroj do izolovaného prostředí,
takže jeho závislosti se nebudou srážet s vašimi projekty.

```bash
# doporučeno: instalace přes pipx
pipx install omi-cli

# nebo přes pip
pip install omi-cli
```

> **Důležité: název balíčku a název příkazu se liší.**
> * Instaluje se balíček **`omi-cli`** (samostatný balíček `omi` je jiný, nesouvisející projekt).
> * Po instalaci se spouští příkaz **`omi`**.

Ověřte, že instalace proběhla:

```bash
omi --version
omi --help
```

---

## 2. Přihlášení

`omi-cli` podporuje dva způsoby přihlášení.

| Způsob | Kdy se hodí | Příkaz |
| :--- | :--- | :--- |
| **Vývojářský klíč (`omi_dev_*`)** | CI/CD, skripty, AI agenti | `omi auth login --api-key ...` nebo proměnná prostředí |
| **Přihlášení přes prohlížeč (Google/Apple)** | Práce na vlastním počítači | `omi auth login --browser` |

### Interaktivní přihlášení

Bez příznaků se příkaz sám zeptá, jakým způsobem se chcete přihlásit:

```bash
omi auth login
# 1) Browser — přihlášení přes Google nebo Apple (pohodlné pro člověka)
# 2) API key — vložit vývojářský klíč z app.omi.me (vhodné pro agenty a CI)
```

Při výběru klíče se vstup maskuje, takže klíč nezůstane v historii terminálu.

### Přímo přes prohlížeč

```bash
omi auth login --browser
```

### Pomocí vývojářského klíče

Klíč získáte na [app.omi.me](https://app.omi.me) v sekci **Developer → API Keys**.

```bash
# uložit klíč do konfigurace
omi auth login --api-key omi_dev_...

# nebo předat přes prostředí — vhodnější pro CI/CD a kontejnery
export OMI_API_KEY=omi_dev_...
```

Proměnná `OMI_API_KEY` se použije, když aktivní profil nemá uložený klíč,
takže v kontejneru nemusíte nic zapisovat na disk. Pokud už je klíč v profilu
uložený, má přednost před proměnnou prostředí.

### Ověření přihlášení

Dva příkazy odpovídají na různé otázky a neměly by se plést:

* `omi auth status` — co je uloženo **lokálně**: profil, maskovaný klíč, platnost.
  Funguje bez sítě.
* `omi auth whoami` — dotaz **na server Omi**: ověří, že klíč skutečně
  server přijímá. Vyžaduje síť.

```bash
omi auth status    # lokální kontrola, offline
omi auth whoami    # ověření na serveru
```

Obnovit klíč s blížícím se koncem platnosti bez opakovaného přihlášení:

```bash
omi auth refresh
```

Odhlášení:

```bash
omi auth logout
```

---

## 3. Základní příkazy

### Vzpomínky (memories)

Fakta a znalosti, které si systém o vás zapamatoval.

```bash
# seznam vzpomínek
omi memory list

# vytvořit novou
omi memory create "Uživatel preferuje tmavý režim" --category lifestyle

# zobrazit konkrétní
omi memory get <MEMORY_ID>
```

### Konverzace (conversations)

Historie řeči a textu ze zařízení nebo z aplikace.

```bash
# posledních 5 konverzací
omi conversation list --limit 5

# celá konverzace včetně přepisu
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Úkoly (action items)

Úkoly, které Omi vytáhlo z konverzací.

```bash
# jen nedokončené
omi action-item list --open

# označit jako splněný
omi action-item complete <ACTION_ITEM_ID>
```

### Cíle (goals)

```bash
# seznam cílů
omi goal list

# zapsat novou hodnotu postupu (potřeba OBA argumenty: cíl i hodnota)
omi goal progress <GOAL_ID> 25

# historie změn
omi goal history <GOAL_ID>
```

---

## Otázka vlastními slovy (`ask`)

Samostatný příkaz nejvyšší úrovně: položí otázku v přirozeném jazyce,
odpověď se skládá z vašich vlastních konverzací.

```bash
omi ask "co jsem rozhodl ohledně stěhování"
omi --json ask "jaké úkoly jsem slíbil tento týden dokončit"
```

---

## 4. JSON a skripty (`--json`)

`omi-cli` umí vracet strojově čitelný JSON. Příznak `--json` je **globální**,
proto se uvádí **před** podpříkazem.

```bash
# vzpomínky: vytáhnout id, text a kategorii
omi --json memory list | jq '.[] | {id, content, category}'

# názvy posledních konverzací
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# nedokončené úkoly
omi --json action-item list --open | jq '.'
```

> **Častá chyba.** `--json` patří před podpříkaz, ne za něj.
> * Správně: `omi --json memory list`
> * Špatně: `omi memory list --json`

V režimu `--json` se na standardní výstup nedostane nic kromě samotného JSON —
na to se dá ve skriptech spolehnout.

---

## 5. Návratové kódy

Kódy jsou stabilní, takže se podle nich dá větvit logika ve skriptech i v CI.

| Kód | Význam | Kdy nastává |
| :---: | :--- | :--- |
| `0` | Úspěch | Příkaz doběhl |
| `1` | Chyba volání | Neplatný příznak, chybí argument |
| `2` | Chyba přístupu | Nepřihlášen, klíč je neplatný nebo prošlý |
| `3` | Chyba serveru | Odpověď 5xx, timeout, žádné spojení |
| `4` | Příliš mnoho požadavků | 429 Too Many Requests |
| `5` | Nenalezeno | 404, zadaný identifikátor neexistuje |

Příklad kontroly v Bashe:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "klíč funguje"
else
  code=$?
  [ "$code" -eq 2 ] && echo "je potřeba se znovu přihlásit"
  [ "$code" -eq 3 ] && echo "server nedostupný, zkusit později"
fi
```

---

## 6. Proměnné prostředí

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_vas_klic"

omi --json memory list --limit 10
```

Aby se klíč načítal i v nových sezeních, přidejte řádek do `~/.bashrc` nebo `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_vas_klic"

# zpracování JSON pomocí PowerShellu
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Trvalé nastavení:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_vas_klic", "User")
```

---

## 7. Lokální aplikace Omi Desktop

Pokud běží desktopová aplikace Omi, část dat je dostupná přímo,
bez obcházení cloudu.

```bash
# nastavit adresu lokálního API
omi local configure --url http://127.0.0.1:47778 --token VAS_TOKEN

# ověřit, že odpovídá
omi --json local status

# hledání v historii obrazovky
omi --json local search-screen "tarify" --days 7 --app Safari

# snímek obrazovky podle identifikátoru
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# libovolný SQL dotaz nad lokální databází
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Postup práce: nejdřív `local status`, pak `local tools` — abyste zjistili dostupné
nástroje a jejich parametry — a teprve potom volání.

---

## 8. Profily

Pokud máte více účtů nebo prostředí, rozdělte je do profilů.
Nastavení se ukládají do `~/.omi/config.toml`.

```bash
# přihlášení do osobního profilu
omi --profile personal auth login

# přihlášení do pracovního
omi --profile work auth login

# spustit příkaz v konkrétním profilu
omi --profile work memory list
```

Zobrazit a změnit samotnou konfiguraci:

```bash
# co je právě nastaveno
omi config show

# kde leží konfigurační soubor
omi config path

# změnit hodnotu
omi config set api_base https://api.omi.me
```

---

## 9. Co dál

* [`agent_quickstart.md`](./agent_quickstart.md) — jak připojit `omi-cli` k AI agentovi.
* [`shell_examples.sh`](./shell_examples.sh) — hotové příklady pro shell.
* [Dokumentace Omi](https://docs.omi.me/doc/developer/cli/introduction) — úplný přehled příkazů.
