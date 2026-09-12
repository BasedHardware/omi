# Ghid de Pornire Rapidă omi-cli (Română)

> Ghid practic pentru interacțiunea cu Omi din terminal. Potrivit atatii pentru oameni, cât și pentru agenți AI.

`omi-cli` este interfața oficială din linia de comandă pentru interacțiunea cu API-urile pentru dezvoltatori ale [Omi](https://omi.me). Gestionează eficient și scriptabil cele patru resurse de bază ale Omi — **amintiri, conversații, elemente de acțiune și obiective**.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentație oficială:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Cod sursă:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalare

Metoda de instalare recomandată folosește `pipx` pentru a izola dependențele.

```bash
# Recomandat: instalați cu pipx
pipx install omi-cli

# Alternativ: utilizați pip
pip install omi-cli
```

> **Important: diferența dintre numele pachetului și numele comenzii**
> * Pachetul Python instalat se numește **`omi-cli`** (pachetul independent `omi` este un alt pachet, fără legătură).
> * Comanda executabilă în terminal după instalare se numește **`omi`**.

După instalare, verificați versiunea și ajutorul.

```bash
omi --version
omi --help
```

---

## 2. Autentificare

`omi-cli` acceptă două metode de autentificare.

| Metodă | Utilizare recomandată | Comandă exemplu |
| :--- | :--- | :--- |
| **Cheie API dezvoltator (`omi_dev_*`)** | CI/CD, scripturi automate, agenți AI | `omi auth login --api-key ...` sau variabilă de mediu |
| **OAuth în browser (Google/Apple)** | PC / laptop dezvoltator | `omi auth login --browser` |

### Autentificare interactivă
Fără opțiuni, vi se va cere să alegeți între autentificarea în browser și introducerea cheii API.

```bash
omi auth login
# 1) Browser — autentificați-vă cu contul Google sau Apple (pentru oameni)
# 2) Cheie API — lipiți cheia de dezvoltator din app.omi.me (pentru agenți/CI)
```

### Autentificare directă prin browser
```bash
omi auth login --browser
```

### Utilizarea cheii API
Obțineți cheia de dezvoltator din **Developer → API Keys** pe [app.omi.me](https://app.omi.me), apoi configurați-o.

```bash
# Setați prin comandă
omi auth login --api-key omi_dev_...

# Sau prin variabilă de mediu (ideal pentru CI/CD sau containere)
export OMI_API_KEY=omi_dev_...
```

### Verificarea stării autentificării
* `omi auth status`: afișează profilul local, token-ul mascat și data expirării (funcționează offline).
* `omi auth whoami`: trimite o cerere reală de autentificare către serverul Omi (necesită conexiune la rețea).

```bash
omi auth status
omi auth whoami
```

Pentru a vă deconecta:
```bash
omi auth logout
```

---

## 3. Utilizare de bază

Puteți lista și gestiona cele patru resurse de bază ale Omi.

### Amintiri (Memories)
Gestionați faptele și cunoștințele învățate de sistem.

```bash
# Listați toate amintirile
omi memory list

# Creați o amintire nouă
omi memory create "Utilizatorul preferă modul întunecat" --category lifestyle

# Afișați detaliile unei amintiri specifice
omi memory get <MEMORY_ID>
```

### Conversații (Conversations)
Istoricul audio sau text al conversațiilor capturate de dispozitivul portabil sau de aplicație.

```bash
# Obțineți ultimele 5 conversații
omi conversation list --limit 5

# Afișați detaliile conversației și transcrierea
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Elemente de acțiune (Action Items)
Sarcini sau elemente de urmărire extrase automat din conversații.

```bash
# Listați doar elementele de acțiune deschise
omi action-item list --open

# Marcați un element de acțiune ca finalizat
omi action-item complete <ACTION_ITEM_ID>
```

### Obiective (Goals)
Gestionați obiectivele al căror progres este urmărit.

```bash
# Listați toate obiectivele
omi goal list
```

---

## 4. Procesarea scripturilor și ieșirea JSON (`--json`)

`omi-cli` acceptă nativ ieșirea JSON. Când o combinați cu `jq` sau scripturi Python, **opțiunea globală** `--json` trebuie plasată înaintea subcomenzii.

```bash
# Obțineți lista amintirilor în JSON și extrageți ID-ul și conținutul
omi --json memory list | jq '.[] | {id, content, category}'

# Obțineți titlurile ultimelor 5 conversații
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Listați elementele de acțiune deschise
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Listați obiectivele
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Diagnosticarea sesiunii

Folosiți aceste două comenzi în pereche pentru depanare rapidă.

```bash
# 1) Verificați mai întâi configurația locală
omi auth status

# 2) Confirmați cu serverul Omi
omi auth whoami

# 3) Dacă este necesar, reporniți autentificarea
omi auth login
```

---

## 6. Cele mai bune practici

* **Folosiți `--json` în scripturi:** Evitați parsarea textului liber; bazați-vă întotdeauna pe ieșirea JSON structurată.
* **Izolați mediile cu `pipx`:** Evita conflictele de dependențe cu alte pachete Python.
* **Nu distribuiți cheile API:** Cheile `omi_dev_*` acordă acces complet la cont — păstrați-le într-un manager de secrete sau în variabile de mediu.
* **Deconectați-vă de pe dispozitivele partajate:** Folosiți `omi auth logout` după sesiuni pe mașini partajate.

---

## 7. Depanare

| Simptom | Cauză probabilă | Soluție |
| :--- | :--- | :--- |
| `command not found: omi` | PATH nu conține directorul bin pipx | Rulați `pipx ensurepath` și reporniți terminalul |
| `401 Unauthorized` | Cheie API invalidă sau expirată | Generați o cheie nouă pe app.omi.me și actualizați |
| `connection refused` | Fără acces la rețea la serverul Omi | Verificați conexiunea la internet și setările proxy |
| `permission denied` pe fișierele de configurare | Directorul de configurare nu poate fi scris | Verificați permisiunile pentru `~/.omi/config.toml` |

---

## 8. Linkuri rapide

* Repository sursă: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Documentație completă: [docs.omi.me](https://docs.omi.me)
* Probleme și asistență: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Comunitatea Discord: invitație disponibilă prin pagina principală Omi