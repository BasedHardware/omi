# omi-cli Priručnik za brzi početak (Bosnian Quickstart)

> Praktično vodilo za korištenje Omi direktno iz terminala — napisano za developere i autonomne AI agente.

`omi-cli` je zvanični command line interface (CLI) za developer API [Omi](https://omi.me). On omogućava strukturiran pristup 4 osnovna resursa Omi: sjećanja (memories), razgovore (conversations), zadatke / akcije (action items) i ciljeve (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Zvanična dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorni kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacija

Da bi izbjegli sukobe sistema zavisnosti i odrzavali izolovano okruženje, jakno preporučujemo korištenje `pipx`:

```bash
# Preporučena metoda: izolovana instalacija preko pipx
pipx install omi-cli

# Alternativna instalacija preko standardnog pip (npr. u virtualnom okruženju)
pip install omi-cli
```

> **Važno raščjavanje: Ime paketa naspram imena komande**
> * Zvanično ime paketa na PyPI je **`omi-cli`** (paket `omi` je odvojen i nepovezan projekat).
> * Komanda koja se izvršava u terminalu je direktno: **`omi`**.

Provjerite je li instalacija uspješna prikazivanjem verzije i pomoćnog menija:

```bash
omi --version
omi --help
```

---

## 2. Autentifikacija

`omi-cli` podržava dva glavna metoda autentifikacije:

| Metod | Namjena | Primjer komande |
| :--- | :--- | :--- |
| **Developer API ključ (`omi_dev_*`)** | Automatizacija, CI/CD, headless serveri, AI agente | `omi auth login --api-key ...` ili `OMI_API_KEY` |
| **OAuth login preko browsera (Google/Apple)** | Lokalni development na ličnom računalu | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktivni login
Izvršavanje komande bez dodatnih parametara pokrece interaktivni meni:

```bash
omi auth login
# 1) Browser - Login s Google preko browsera (za login s Apple koristite flag `--provider apple`)
# 2) API key - Unos developer API ključ sa app.omi.me
```

### Direktni login preko browsera
```bash
# Standardni login s Google nalogom
omi auth login --browser

# Alternativni login s Apple profilom
omi auth login --browser --provider apple
```

### Login s developer API ključem
Generisite API ključ sa kontrolne table [app.omi.me](https://app.omi.me) u sekciji **Developer -> API Keys**:

```bash
# Sačuvaj ključ u trenutni lokalni profil
omi auth login --api-key omi_dev_...

# Ili preko exportovanja environment varijable (idealno za Docker kontejnere i CI/CD):
# Napomena: Ako profil vec ima sačuvan ključ, prvo izvršite `omi auth logout`.
export OMI_API_KEY="omi_dev_vaš_ključ_ovdje"
```

### Provjera statusa autentifikacije
* `omi auth status`: Pokazuje aktivan profil i maskovan ID bez mrežnog zahtjeva (radi offline).
* `omi auth whoami`: Salije validacijski zahtjev na Omi server za potvrdu validnosti sesije (zahtijeva internet vezu).

```bash
omi auth status
omi auth whoami
```

### Odjava (Logout)
```bash
omi auth logout
# Ako ste koristili environment varijablu OMI_API_KEY, uklonite je iz sesije. U Bash/Zsh koristite: unset OMI_API_KEY
```

---

## 3. Osnovne komande

### Sjećanja (Memories)
Kontekstualne bilješke i opservacije sačuvane od strane Omi:

```bash
# Ispis liste sačuvanih sjećanja
omi memory list

# Kreiranje novog sjećanja
omi memory create "Preferira kratke i tehnički precizne odgovore s primjerima u Pythonu" --category work

# Izdvajanje konkretnog sjećanja po ID
omi memory get <MEMORY_ID>
```

### Razgovori (Conversations)
Sačuvani razgovori i transkripti sa Omi uređaja:

```bash
# Lista posljednjih 5 razgovora
omi conversation list --limit 5

# Izdvajanje razgovora zajedno sa potpunim transkriptom
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Zadaci i akcije (Action Items)
Automatski prepoznati zadaci iz vođenih razgovora:

```bash
# Ispis otvorenih zadataka
omi action-item list --open

# Oznacavanje zadataka kao završene
omi action-item complete <ACTION_ITEM_ID>
```

### Ciljevi (Goals)
Dugoročni ciljevi i praćenje napredka:

```bash
# Lista aktivnih ciljeva
omi goal list

# Kreiranje kvantitativnog cilja
omi goal create "Pij 2 litra vode dnevno" --type numeric --target 2 --unit liters
```

---

## 4. Strukturirana automatizacija i JSON izlaz (`--json`)

`omi-cli` je optimiziran za skriptnu integraciju i napajanje AI agenata. Globalni flag `--json` vraća validan JSON format za obradu sa alatima poput `jq`:

```bash
# Lista sjećanja u JSON formatu i filtriranje s jq
omi --json memory list | jq '.[] | {id, content, category}'

omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

omi --json action-item list --open | jq '.'
```

> **Važno pravilo sintakse:**
> Flag `--json` je **globalna opcija**, to znači da mora biti postavljen **prije** podkomande:
> * Ispravno: `omi --json memory list`
> * Pogrešno: `omi memory list --json`

### Paginacija i export u fajlove
Koristite parametre `--limit` i `--offset` za pregled velikih zapremine podataka:

```bash
# Paginacija rezultata
omi --json memory list --limit 25 --offset 0 > sjecioci-stranica-1.json
omi --json memory list --limit 25 --offset 25 > sjecioci-stranica-2.json
```

Redirekcija u fajl preuzima ili kreira fajl lokalno. Uvijek provjerite exit kod komande prije obrade. Greške se ispisuju u standardni tok greške (stderr), to znači da prazan fajl ne garantuje odsustvo podataka. Exportovani fajlovi mogu sadržavati lične podatke - čuvajte ih u skladu sa svojim sigurnosnim politikama.

---

## 5. Exit kodovi (Exit Codes)

Pouzdana obrada grešaka u CLI skriptama i CI/CD cevovima:

| Kod | Značaj | Opis |
| :---: | :--- | :--- |
| `0` | **Uspjeh (`EXIT_OK`)** | Komanda izvršena uspješno bez grešaka. |
| `1` | **Greška korištenja / sintakse (`EXIT_USAGE`)** | Nevalidne vrijednosti, nepoznati Click flagovi ili nedostajući argumenti. |
| `2` | **Greška autentifikacije (`EXIT_AUTH`)** | Nedostajući podaci o identitetu, istekli ključ ili nepostojeće dozvole. |
| `3` | **Server ili mrežna greška (`EXIT_SERVER`)** | HTTP 5xx odgovor, prekid veze ili timeout zahtjeva. |
| `4` | **Ograničenje zahtjeva (`EXIT_RATE_LIMITED`)** | HTTP 429 odgovor - preveliki broj zahtjeva u kratkom vremenskom periodu. |
| `5` | **Resurs nije pronađen (`EXIT_NOT_FOUND`)** | HTTP 404 odgovor - traženi objekat ne postoji. |

---

## 6. Primjeri za različita terminalna okruženja

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_vaš_ključ_ovdje"

# Izvršavanje komande i provjera exit koda
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Došlo je do greške pri izvršavanju komande." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_vaš_ključ_ovdje"

# Konverzija JSON izlaza direktno u PowerShell objekat
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Provjera greške preko $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi komanda je završila s greškom: $LASTEXITCODE."
}
```

---

## 7. Integracija s lokalnim Desktop API (Local Desktop API)

Ako je Omi desktop aplikacija pokrenuta na istom računalu, može se saljati zahtjevi prema lokalnoj vremenskoj historiji bez pristupa oblaku:

```bash
# Postavljanje lokalne adrese i pristupnog tokena
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Unesi desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Provjera statusa lokalne usluge
omi --json local status

# Pretraga ekranne vremenske historije
omi --json local search-screen "Kvartalni izvještaj" --days 7 --app Safari
```

---

## 8. Rad sa većim brojem profila (Profiles)

Flag `--profile` omogućava razdvajanje poslovnih, ličnih naloga ili testirajućih okruženja. Konfiguracije se čuvaju u `~/.omi/config.toml`:

```bash
# Kreiranje i login u licni profil
omi --profile personal auth login

# Kreiranje i login u poslovni profil
omi --profile work auth login

# Izvršavanje komande sa određenim profilom
omi --profile work memory list

# Korištenje staging okruženja
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Sigurnost i dobre prakse

* **Ne čuvajte ključeve u Git-u:** Nikada ne dodavajte API ključeve u javna repozitorija; koristite menadžera tajni ili fajlove okruženja definisane u `.gitignore`.
* **Zaštita terminalne historije:** Na dijeljenim mašinama izbjegavajte prosljeđivanje ključeva kao argumenata komandi; koristite interaktivni login ili varijablu `OMI_API_KEY`.
* **Dozvole za fajlove:** U Unix okruženjima postavite restrikcijske dozvole na konfiguracioni direktorij `~/.omi/` (chmod 700 ~/.omi).




