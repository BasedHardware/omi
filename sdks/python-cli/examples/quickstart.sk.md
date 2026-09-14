# omi-cli — rýchly štart v slovenčine

> Praktická príručka práce s Omi z terminálu. Hodí sa pre človeka aj pre AI agenta.

`omi-cli` je oficiálne rozhranie príkazového riadku pre vývojárske API [Omi](https://omi.me).
Poskytuje rýchly a skriptovateľný prístup ku štyrom hlavným entitám Omi:
spomienkam (memories), konverzáciám (conversations), úlohám (action items) a cieľom (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentácia:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Zdrojový kód:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Inštalácia

Odporúčaný spôsob je `pipx`: nainštaluje nástroj do izolovaného prostredia,
takže jeho závislosti sa nebudú biť s vašimi projektmi.

```bash
# odporúčané: inštalácia cez pipx
pipx install omi-cli

# alebo cez pip
pip install omi-cli
```

> **Dôležité: názov balíka a názov príkazu sa líšia.**
> * Inštaluje sa balík **`omi-cli`** (samostatný balík `omi` je iný, nesúvisiaci projekt).
> * Po inštalácii sa spúšťa príkaz **`omi`**.

Overte, že inštalácia prebehla:

```bash
omi --version
omi --help
```

---

## 2. Prihlásenie

`omi-cli` podporuje dva spôsoby prihlásenia.

| Spôsob | Kedy sa hodí | Príkaz |
| :--- | :--- | :--- |
| **Vývojársky kľúč (`omi_dev_*`)** | CI/CD, skripty, AI agenti | `omi auth login --api-key ...` alebo premenná prostredia |
| **Prihlásenie cez prehliadač (Google/Apple)** | Práca na vlastnom počítači | `omi auth login --browser` |

### Interaktívne prihlásenie

Bez príznakov sa príkaz sám spýta, akým spôsobom sa chcete prihlásiť:

```bash
omi auth login
# 1) Browser — prihlásenie cez Google alebo Apple (pohodlné pre človeka)
# 2) API key — vložiť vývojársky kľúč z app.omi.me (vhodné pre agentov a CI)
```

Pri výbere kľúča sa vstup maskuje, takže kľúč nezostane v histórii terminálu.

### Priamo cez prehliadač

```bash
omi auth login --browser
```

### Pomocou vývojárskeho kľúča

Kľúč získate na [app.omi.me](https://app.omi.me) v sekcii **Developer → API Keys**.

```bash
# uložiť kľúč do konfigurácie
omi auth login --api-key omi_dev_...

# alebo ho odovzdať cez prostredie — lepšie pre CI/CD a kontajnery
export OMI_API_KEY=omi_dev_...
```

Premenná `OMI_API_KEY` sa použije, keď aktívny profil nemá uložený kľúč,
takže v kontajneri nemusíte nič zapisovať na disk. Ak už je kľúč v profile
uložený, má prednosť pred premennou prostredia.

### Overenie prihlásenia

Dva príkazy odpovedajú na rôzne otázky a nemali by sa zamieňať:

* `omi auth status` — čo je uložené **lokálne**: profil, maskovaný kľúč, platnosť.
  Funguje bez siete.
* `omi auth whoami` — dotaz **na server Omi**: overí, že kľúč skutočne
  server akceptuje. Vyžaduje sieť.

```bash
omi auth status    # lokálna kontrola, offline
omi auth whoami    # overenie na serveri
```

Obnoviť kľúč s blížiacim sa koncom platnosti bez opätovného prihlásenia:

```bash
omi auth refresh
```

Odhlásenie:

```bash
omi auth logout
```

---

## 3. Základné príkazy

### Spomienky (memories)

Fakty a vedomosti, ktoré si systém o vás zapamätal.

```bash
# zoznam spomienok
omi memory list

# vytvoriť novú
omi memory create "Používateľ preferuje tmavý režim" --category lifestyle

# zobraziť konkrétnu
omi memory get <MEMORY_ID>
```

### Konverzácie (conversations)

História reči a textu zo zariadenia alebo z aplikácie.

```bash
# posledných 5 konverzácií
omi conversation list --limit 5

# celá konverzácia vrátane prepisu
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Úlohy (action items)

Úlohy, ktoré Omi vytiahol z konverzácií.

```bash
# len nedokončené
omi action-item list --open

# označiť ako splnenú
omi action-item complete <ACTION_ITEM_ID>
```

### Ciele (goals)

```bash
# zoznam cieľov
omi goal list

# zapísať novú hodnotu postupu (treba OBA argumenty: cieľ aj hodnota)
omi goal progress <GOAL_ID> 25

# história zmien
omi goal history <GOAL_ID>
```

---

## Otázka vlastnými slovami (`ask`)

Samostatný príkaz najvyššej úrovne: položí otázku v prirodzenom jazyku,
odpoveď sa skladá z vašich vlastných konverzácií.

```bash
omi ask "čo som rozhodol ohľadom sťahovania"
omi --json ask "aké úlohy som sľúbil tento týždeň dokončiť"
```

---

## 4. JSON a skripty (`--json`)

`omi-cli` vie vracať strojovo čitateľný JSON. Príznak `--json` je **globálny**,
preto sa uvádza **pred** podpríkazom.

```bash
# spomienky: vytiahnuť id, text a kategóriu
omi --json memory list | jq '.[] | {id, content, category}'

# názvy posledných konverzácií
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# nedokončené úlohy
omi --json action-item list --open | jq '.'
```

> **Častá chyba.** `--json` patrí pred podpríkaz, nie za neho.
> * Správne: `omi --json memory list`
> * Nesprávne: `omi memory list --json`

V režime `--json` sa na štandardný výstup nedostane nič okrem samotného JSON —
na to sa dá v skriptoch spoľahnúť.

---

## 5. Návratové kódy

Kódy sú stabilné, takže sa podľa nich dá vetviť logika v skriptoch aj v CI.

| Kód | Význam | Kedy nastáva |
| :---: | :--- | :--- |
| `0` | Úspech | Príkaz dobehol |
| `1` | Chyba volania | Neplatný príznak, chýba argument |
| `2` | Chyba prístupu | Neprihlásený, kľúč je neplatný alebo prešlý |
| `3` | Chyba servera | Odpoveď 5xx, timeout, žiadne spojenie |
| `4` | Priveľa požiadaviek | 429 Too Many Requests |
| `5` | Nenájdené | 404, zadaný identifikátor neexistuje |

Príklad kontroly v Bashe:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "kľúč funguje"
else
  code=$?
  [ "$code" -eq 2 ] && echo "treba sa znova prihlásiť"
  [ "$code" -eq 3 ] && echo "server nedostupný, skúste neskôr"
fi
```

---

## 6. Premenné prostredia

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_vas_kluc"

omi --json memory list --limit 10
```

Aby sa kľúč načítaval aj v nových reláciách, pridajte riadok do `~/.bashrc` alebo `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_vas_kluc"

# spracovanie JSON pomocou PowerShellu
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Trvalé nastavenie:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_vas_kluc", "User")
```

---

## 7. Lokálna aplikácia Omi Desktop

Ak beží desktopová aplikácia Omi, časť dát je dostupná priamo,
bez obchádzania cloudu.

```bash
# nastaviť adresu lokálneho API
omi local configure --url http://127.0.0.1:47778 --token VAS_TOKEN

# overiť, že odpovedá
omi --json local status

# hľadanie v histórii obrazovky
omi --json local search-screen "tarify" --days 7 --app Safari

# snímka obrazovky podľa identifikátora
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# ľubovoľný SQL dotaz nad lokálnou databázou
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Postup práce: najprv `local status`, potom `local tools` — aby ste zistili dostupné
nástroje a ich parametre — a až potom volania.

---

## 8. Profily

Ak máte viac účtov alebo prostredí, rozdeľte ich do profilov.
Nastavenia sa ukladajú do `~/.omi/config.toml`.

```bash
# prihlásenie do osobného profilu
omi --profile personal auth login

# prihlásenie do pracovného
omi --profile work auth login

# spustiť príkaz v konkrétnom profile
omi --profile work memory list
```

Zobraziť a meniť samotnú konfiguráciu:

```bash
# čo je práve nastavené
omi config show

# kde leží konfiguračný súbor
omi config path

# zmeniť hodnotu
omi config set api_base https://api.omi.me
```

---

## 9. Čo ďalej

* [`agent_quickstart.md`](./agent_quickstart.md) — ako pripojiť `omi-cli` k AI agentovi.
* [`shell_examples.sh`](./shell_examples.sh) — hotové príklady pre shell.
* [Dokumentácia Omi](https://docs.omi.me/doc/developer/cli/introduction) — úplný prehľad príkazov.
