# omi-cli — ghid rapid în română

> Ghid practic pentru a lucra cu Omi din terminal. Potrivit atât pentru oameni, cât și pentru agenți AI.

`omi-cli` este clientul oficial de linie de comandă pentru API-ul pentru dezvoltatori [Omi](https://omi.me).
Oferă acces rapid și scriptabil la cele patru entități principale Omi:
amintiri, conversații, elemente de acțiune și obiective.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentație:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Cod sursă:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalare

Metoda recomandată este `pipx`: instalează instrumentul într-un mediu izolat,
astfel încât dependențele sale nu intră în conflict cu proiectele dvs.

```bash
# recomandat: instalare cu pipx
pipx install omi-cli

# sau cu pip
pip install omi-cli
```

> **Important: numele pachetului și numele comenzii sunt diferite.**
> * Pachetul instalat este **`omi-cli`** (pachetul separat `omi` este un alt proiect, neînrudit).
> * După instalare se execută comanda **`omi`**.

Verificați că totul funcționează:

```bash
omi --version
omi --help
```

---

## 2. Autentificare

`omi-cli` acceptă două metode de autentificare.

| Metodă | Potrivită pentru | Comandă |
| :--- | :--- | :--- |
| **Cheie de dezvoltator (`omi_dev_*`)** | CI/CD, scripturi, agenți AI | `omi auth login --api-key ...` sau variabilă de mediu |
| **Autentificare prin browser (Google/Apple)** | Lucru pe propriul computer | `omi auth login --browser` |

### Autentificare interactivă

Rulați fără opțiuni și va întreba ce metodă să folosiți.

```bash
omi auth login
# 1) Browser — autentificare cu Google sau Apple (pentru oameni)
# 2) API key — lipiți cheia de dezvoltator de pe app.omi.me (pentru agenți/CI)
```

Dacă alegeți cheia, introducerea este ascunsă, astfel încât cheia nu rămâne în istoricul terminalului.

### Autentificare directă prin browser

```bash
omi auth login --browser
```

### Autentificare cu cheie de dezvoltator

Obțineți cheia pe [app.omi.me](https://app.omi.me) la **Developer → API Keys**.

```bash
# salvați cheia în configurație
omi auth login --api-key omi_dev_...

# sau transmiteți-o prin mediu — mai bun pentru CI/CD și containere
export OMI_API_KEY=omi_dev_...
```

Variabila de mediu `OMI_API_KEY` este folosită atunci când în profilul activ nu este
salvată nicio cheie, deci într-un container nu trebuie scris nimic pe disc. Dacă profilul
are deja o cheie, aceasta are prioritate față de variabila de mediu.

### Verificați accesul

Două comenzi răspund la întrebări diferite și nu trebuie confundate:

* `omi auth status` — ce este salvat **local**: profil, cheie mascată, dată de expirare.
  Funcționează fără rețea.
* `omi auth whoami` — cerere **către serverul Omi**: verifică dacă cheia este într-adevăr acceptată.
  Necesită rețea.

```bash
omi auth status    # verificare locală, offline
omi auth whoami    # verificare pe server
```

Reîmprospătați un jeton aproape expirat fără o nouă autentificare — această comandă
este valabilă **numai pentru sesiunile de browser/OAuth**. Pentru un profil autentificat
cu o cheie API (`omi_dev_*`), `omi auth refresh` eșuează cu o eroare de utilizare
(codul 1): nu există un jeton de reîmprospătat — schimbați cheia în aplicația web Omi
dacă este necesar:

```bash
omi auth refresh
```

Deconectare:

```bash
omi auth logout
```

---

## 3. Comenzi de bază

### Amintiri (memories)

Fapte și cunoștințe pe care sistemul le-a reținut despre dvs.

```bash
# lista amintirilor
omi memory list

# creați una nouă
omi memory create "Utilizatorul preferă tema întunecată" --category lifestyle

# vizualizați una anume
omi memory get <MEMORY_ID>
```

### Conversații (conversations)

Istoricul audio și text de pe dispozitiv sau din aplicație.

```bash
# cele mai recente 5 conversații
omi conversation list --limit 5

# o conversație completă cu transcriere
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Elemente de acțiune (action items)

Sarcini pe care Omi le-a dedus din conversații.

```bash
# doar cele deschise
omi action-item list --open

# marcați ca finalizată
omi action-item complete <ACTION_ITEM_ID>
```

### Obiective (goals)

```bash
# lista obiectivelor
omi goal list

# înregistrați o nouă valoare de progres (necesită AMBELE argumente: obiectiv și valoare)
omi goal progress <GOAL_ID> 25

# istoricul modificărilor
omi goal history <GOAL_ID>
```

---

## Întrebați în limbaj natural (`ask`)

O comandă separată de nivel superior: primește o întrebare în limbaj natural,
iar răspunsul este construit din conversațiile dvs.

```bash
omi ask "ce am decis despre mutare"
omi --json ask "ce elemente de acțiune am promis să finalizez săptămâna aceasta"
```

---

## 4. JSON și scripturi (`--json`)

`omi-cli` poate produce JSON citibil de mașină. Opțiunea `--json` este **globală**
și trebuie plasată **înainte** de subcomandă.

```bash
# amintiri: extrageți id, text și categorie
omi --json memory list | jq '.[] | {id, content, category}'

# titlurile conversațiilor recente
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# elemente de acțiune deschise
omi --json action-item list --open | jq '.'
```

> **Eroare frecventă.** `--json` vine înainte de subcomandă, nu după.
> * Corect: `omi --json memory list`
> * Greșit: `omi memory list --json`

În modul `--json`, mesajele de progres și spinner-ele pentru oameni dispar —
stdout conține doar un document JSON valid. Erorile merg la stderr
în forma `{"error": "...", "detail": "..."}`.

---

## 5. Coduri de ieșire

Coduri de ieșire stabile pentru ramificarea în scripturi.

| Cod | Semnificație |
| :--- | :--- |
| `0` | Succes |
| `1` | Eroare de utilizare (steag greșit, argument obligatoriu lipsă) |
| `2` | Autentificare eșuată — autentificare necesară |
| `3` | Eroare de server/rețea |
| `4` | Limită de rată — reîncercați mai târziu |
| `5` | Resursă negăsită |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "această amintire nu există" ;;
    *) echo "eroare $code" ;;
  esac
fi
```

---

## 6. Profiluri și configurație

Dacă aveți mai multe conturi sau medii, separați-le cu profiluri.
Setările sunt salvate în `~/.omi/config.toml`.

```bash
# autentificare în profilul personal
omi --profile personal auth login

# autentificare în profilul de serviciu
omi --profile work auth login

# rulați o comandă într-un profil anume
omi --profile work memory list
```

Profilul utilizat este determinat în această ordine: opțiunea `--profile` (sau `-p`)
are prioritate față de toate; apoi variabila de mediu `OMI_PROFILE`; apoi profilul
activ din `~/.omi/config.toml`; și în final profilul `default` ca rezervă.

Vizualizați și modificați configurația însăși:

```bash
# ce este configurat acum
omi config show

# unde este fișierul de configurare
omi config path

# modificați o valoare
omi config set api_base https://api.omi.me
```

---

## 7. Pașii următori

* [`agent_quickstart.md`](./agent_quickstart.md) — cum să conectați `omi-cli` la un agent AI.
* [`shell_examples.sh`](./shell_examples.sh) — exemple de shell gata de utilizare.
* [Documentația Omi](https://docs.omi.me/doc/developer/cli/introduction) — referința completă a comenzilor.
