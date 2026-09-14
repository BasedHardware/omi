# omi-cli Prirucnik za brzi pokret (Bosnian Quickstart)

> Prakticno vodilo za koristenje Omi direktno iz terminala - napisano za developere i autonomne AI agende.

`omi-cli` je zvanicni command line interface (CLI) za developer API [Omi](https://omi.me). On omogucava strukturiran pristup 4 osnovna resursa Omi: sjececi (memories), razgovore (conversations), zadatke / akcije (action items) i ciljeve (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Zvanicna dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorni kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacija

Da bi izbjegli sukobe sistema zavisnosti i odrzavali izolovano okruzenje, jacno preporucujemo koristenje `pipx`:

```bash
# Preporucena metoda: izolovana instalacija preko pipx
pipx install omi-cli

# Alternativna instalacija preko standardnog pip (npr. u virtualnom okruzenju)
pip install omi-cli
```

> **Vazno razjasnjenje: Ime paketa naspram imena komande**
> * Zvanicno ime paketa na PyPI je **`omi-cli`** (paket `omi` je odvojen i nepovezan projekat).
> * Komanda koja se izvrsava u terminalu je direktno: **`omi`**.

Provjerite je li instalacija uspjesna prikazivanjem verzije i pomocnog menija:

```bash
omi --version
omi --help
```

---

## 2. Autentifikacija

`omi-cli` podrzava dva glavna metoda autentifikacije:

| Metod | Namjena | Primjer komande |
| :--- | :--- | :--- |
| **Developer API kljuc (`omi_dev_*`)** | Automatizacija, CI/CD, headless serveri, AI agende | `omi auth login --api-key ...` ili `OMI_API_KEY` |
| **OAuth login preko browsera (Google/Apple)** | Lokalni development na licnom racunalu | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktivni login
Izvršavanje komande bez dodatnih parametara pokrece interaktivni meni:

```bash
omi auth login
# 1) Browser - Login s Google preko browsera (za login s Apple koristite flag `--provider apple`)
# 2) API key - Unos developer API kljuc sa app.omi.me
```

### Direktni login preko browsera
```bash
# Standardni login s Google nalogom
omi auth login --browser

# Alternativni login s Apple profilom
omi auth login --browser --provider apple
```

### Login s developer API kljucem
Generisite API kljuc sa kontrolne table [app.omi.me](https://app.omi.me) u sekciji **Developer -> API Keys**:

```bash
# Sacuvaj kljuc u trenutni lokalni profil
omi auth login --api-key omi_dev_...

# Ili preko exportovanja environment varijable (idealno za Docker kontejnere i CI/CD):
# Napomena: Ako profil vec ima sacuvan kljuc, prvo izvrsite `omi auth logout`.
export OMI_API_KEY="omi_dev_vas_kljuc_ovdje"
```

### Provjera statusa autentifikacije
* `omi auth status`: Pokazuje aktivan profil i maskovan ID bez mreznog zahtjeva (radi offline).
* `omi auth whoami`: Slaze validacijski zahtjev na Omi server za potvrdu validnosti sesije (zahtijeva internet vezu).

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

### Sjececi (Memories)
Kontekstualne biljeske i opservacije sacuvane od strane Omi:

```bash
# Ispis liste sacuvanih sjececa
omi memory list

# Kreiranje novog sjececa
omi memory create "Prefers short and technically solid answers with Python examples" --category work

# Izdvajanje konkretnog sjececa po ID
omi memory get <MEMORY_ID>
```

### Razgovori (Conversations)
Sacuvani razgovori i transkripti sa Omi uredjaja:

```bash
# Lista poslednjih 5 razgovora
omi conversation list --limit 5

# Izdvajanje razgovora zajedno sa potpunim transkriptom
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Zadaci i akcije (Action Items)
Automatski prepoznati zadaci iz vodjenih razgovora:

```bash
# Ispis otvorenih zadataka
omi action-item list --open

# Oznacavanje zadataka kao završene
omi action-item complete <ACTION_ITEM_ID>
```

### Ciljevi (Goals)
Dugorocni ciljevi i praćenje napredka:

```bash
# Lista aktivnih ciljeva
omi goal list

# Kreiranje kvantitativnog cilja
omi goal create "Pij 2 litra vode dnevno" --type numeric --target 2 --unit liters
```

---

## 4. Strukturirana automatizacija i JSON izlaz (`--json`)

`omi-cli` je optimiziran za skriptnu integraciju i napajanje AI agenata. Globalni flag `--json` vracva validan JSON format za obradu sa alatima poput `jq`:

```bash
# Lista sjececa u JSON formatu i filtriranje s jq
omi --json memory list | jq '.[] | {id, content, category}'

omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

omi --json action-item list --open | jq '.'
```

> **Vazno pravilo sintakse:**
> Flag `--json` je **globalna opcija**, sto znaci da mora biti postavljen **prije** podkomande:
> * Ispravno: `omi --json memory list`
> * Pogresno: `omi memory list --json`

### Paginacija i export u fajlove
Koristite parametre `--limit` i `--offset` za pregled velikih zapremina podataka:

```bash
# Paginacija rezultata
omi --json memory list --limit 25 --offset 0 > sjececi-stranica-1.json
omi --json memory list --limit 25 --offset 25 > sjececi-stranica-2.json
```

Redirekcija u fajl preuziva ili kreira fajl lokalno. Uvijek provjerite exit kod komande prije obrade. Greske se ispisuju u standardni tok greske (stderr), sto znaci da prazan fajl ne garantuje odsustvo podataka. Exportovani fajlovi mogu sadrzavati licne podatke - cuvajte ih u skladu sa svojim sigurnosnim politikama.

---

## 5. Exit kodovi (Exit Codes)

Pouzdana obrada gresaka u CLI skriptama i CI/CD cevovima:

| Kod | Znacaj | Opis |
| :---: | :--- | :--- |
| `0` | **Uspjeh (`EXIT_OK`)** | Komanda izvrsena uspjesno bez gresaka. |
| `1` | **Greska koristenja / sintakse (`EXIT_USAGE`)** | Nevalidne vrijednosti, nepoznati Click flagovi ili nedostajuci argumenti. |
| `2` | **Greska autentifikacije (`EXIT_AUTH`)** | Nedostajuci podaci o identitetu, istekli kljuc ili nepostojuci dozvole. |
| `3` | **Server ili mrezna greska (`EXIT_SERVER`)** | HTTP 5xx odgovor, prekid veze ili timeout zahtjeva. |
| `4` | **Ogranicenje zahtjeva (`EXIT_RATE_LIMITED`)** | HTTP 429 odgovor - preveliki broj zahtjeva u kratkom vremenskom periodu. |
| `5` | **Resurs nije pronadjen (`EXIT_NOT_FOUND`)** | HTTP 404 odgovor - trazeni objekat ne postoji. |

---

## 6. Primjeri za razlicita terminalna okruzenja

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_vas_kljuc_ovdje"

# Izvršavanje komande i provjera exit koda
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Doslo je do greske pri izvrsavanju komande." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_vas_kljuc_ovdje"

# Konverzija JSON izlaza direktno u PowerShell objekat
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Provjera greske preko $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi komanda je zavrsila s greskom: $LASTEXITCODE."
}
```

---

## 7. Integracija s lokalnim Desktop API (Local Desktop API)

Ako je Omi desktop aplikacija pokrenuta na istom racunalu, moze se saljati zahtjevi prema lokalnoj vremenskoj historiji bez pristupa oblaku:

```bash
# Postavljanje lokalne adrese i pristupnog tokena
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Unesi desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Provjera statusa lokalne usluge
omi --json local status

# Pretraga ekranne vremenske historije
omi --json local search-screen "Kvartalni izvjestaj" --days 7 --app Safari
```

---

## 8. Rad sa većim brojem profila (Profiles)

Flag `--profile` omogucava razdvajanje poslovnih, licnih naloga ili testirajucih okruzenja. Konfiguracija se cuvaju u `~/.omi/config.toml`:

```bash
# Kreiranje i login u licni profil
omi --profile personal auth login

# Kreiranje i login u poslovni profil
omi --profile work auth login

# Izvršavanje komande sa odredjenim profilom
omi --profile work memory list

# Koristenje staging okruzenja
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Sigurnost i dobre prakse

* **Ne cuvajte kljuceve u Git-u:** Nikada ne dodavajte API kljuceve u javna repozitorija; koristite menadzera tajni ili fajlove okruzenja definisane u `.gitignore`.
* **Zastita terminalne historije:** Na dijeljenim masinama izbjegavajte prosledjivanje kljuceva kao argumenata komandi; koristite interaktivni login ili varijablu `OMI_API_KEY`.
* **Dozvole za fajlove:** U Unix okruzenjima postavite restrikcijske dozvole na konfiguracioni direktorij `~/.omi/` (chmod 700 ~/.omi).




