# omi-cli — Vodič za brzi početak (Serbian Quickstart)

> Praktičan vodič za upravljanje Omijem direktno iz terminala — namenjen programerima i autonomnim AI agentima.

`omi-cli` je zvanični interfejs komandne linije (CLI) za programerski API servisa [Omi](https://omi.me). Pruža brz, skriptabilan i strukturiran pristup četirima osnovnim resursima koje Omi vodi o vama:

* **Sećanja (memories)** — činjenice, zapažanja i znanja koja sistem pamti o vama
* **Razgovori (conversations)** — zabeleženi i obrađeni audio ili tekstualni dijalozi
* **Akcione stavke (action items)** — zadaci, zaduženja i prepoznate obaveze
* **Ciljevi (goals)** — praćeni ciljevi i metrike napretka

Namerno je dizajniran da bude kompaktan, lak za automatizaciju i orijentisan ka JSON formatu — sve što vam je potrebno za integraciju Omija u Unix cevovode (pipelines), CI poslove, radne okvire za AI agente ili sopstvene skripte.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Zvanična dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorni kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacija

Preporučeni način instalacije je putem alata `pipx`. On instalira paket u izolovano okruženje, čime se sprečava konflikt zavisnosti sa drugim sistemskim ili projektim paketima:

```bash
# Preporučeno: instalacija putem alata pipx
pipx install omi-cli

# Ili putem standardnog pip alata (npr. unutar virtuelnog okruženja)
pip install omi-cli
```

> **Važna razlika: Naziv paketa i naziv izvršne komande se razlikuju.**
> * Paket koji instalirate sa PyPI repozitorijuma se zove **`omi-cli`** (samostalni paket pod nazivom `omi` pripada drugom projektu).
> * Komanda koju pokrećete u terminalu nakon instalacije glasi **`omi`**.

Provera uspešne instalacije:

```bash
omi --version
omi --help
```

---

## 2. Autentifikacija

`omi-cli` podržava dva načina prijave:

| Metod | Pogodno za | Način pokretanja |
| :--- | :--- | :--- |
| **Razvojni API ključ (`omi_dev_*`)** | Skripte, CI/CD, automatizaciju i AI agente | `omi auth login --api-key ...` ili promenljiva okruženja |
| **Prijava preko pregledača (Google / Apple)** | Lični rad na računaru | `omi auth login --browser` |

### Interaktivna prijava

Ako pokrenete komandu bez dodatnih parametara, `omi-cli` će vas interaktivno upitati za izbor metoda:

```bash
omi auth login
# 1) Browser — prijava putem Google ili Apple naloga (za korisnike)
# 2) API key — unos razvojnog ključa sa app.omi.me (za agente i CI)
```

Prilikom izbora API ključa unos u terminalu je maskiran, tako da tajni ključ ne ostaje sačuvan u istoriji komandi ljuske.

### Direktna prijava preko veb pregledača

```bash
# Podrazumevani provajder je Google
omi auth login --browser

# Ili eksplicitno putem Apple naloga
omi auth login --browser --provider apple
```

Ova opcija pokreće vaš podrazumevani veb pregledač radi OAuth autentifikacije i prihvata odgovor na lokalnoj povratnoj adresi (`localhost`). Pristupni tokeni se bezbedno čuvaju u konfiguracionoj datoteci `~/.omi/config.toml`.

### Prijava putem razvojnog API ključa

Razvojni ključ možete generisati na veb portalu [app.omi.me](https://app.omi.me) u odeljku **Developer → API Keys**.

```bash
# Čuvanje ključa u lokalnu konfiguraciju profila
omi auth login --api-key omi_dev_vas_kljuc_ovde

# Ili prosleđivanje putem cevi (npr. u CI skriptama)
omi auth login < kljuc.txt

# Ili postavljanje kroz promenljivu okruženja (preporučeno za kontejnere i CI)
export OMI_API_KEY="omi_dev_vas_kljuc_ovde"
```

Promenljiva okruženja `OMI_API_KEY` se koristi kada u aktivnom profilu nije sačuvan ključ, što omogućava rad u kontejnerima bez upisivanja fajlova na disk. Ukoliko je ključ već snimljen u profilu, on ima prednost nad promenljivom okruženja.

### Provera statusa prijave

Dve komande daju različite nivoe provere:

* `omi auth status` — prikazuje **lokalno sačuvano stanje**: naziv profila, maskirani ključ i datum isteka. Radi potpuno oflajn, bez pristupa mreži.
* `omi auth whoami` — upućuje **zahtev ka Omi serveru** kako bi se potvrdilo da server prihvata vaše kredencijale. Zahteva aktivnu internet vezu.

```bash
omi auth status    # lokalna provera (bez mreže)
omi auth whoami    # provera na serveru
```

### Osvežavanje tokena i odjava

Komanda `omi auth refresh` služi za obnavljanje tokena koji uskoro ističu, ali je podržana **isključivo za sesije veb pregledača (OAuth)**. Ukoliko se pozove nad profilom koji koristi API ključ (`omi_dev_*`), komanda vraća grešku pri upotrebi (izlazni kod 1) jer API ključevi nemaju mehanizam osvežavanja tokena.

```bash
# Osvežavanje OAuth sesije
omi auth refresh

# Brisanje sačuvanih kredencijala sa lokalnog sistema
omi auth logout
```

Konfiguracija i sesije se podrazumevano čuvaju u `~/.omi/config.toml`. Čuvajte ovu datoteku i nemojte je deliti.

---

## 3. Osnovne komande

### Sećanja (Memories)

Sećanja su pojedinačne činjenice i zapažanja koje sistem usvaja o vama.

```bash
# Prikaz najnovijih sećanja (podrazumevano 25)
omi memory list

# Ograničavanje broja stavki
omi memory list --limit 5

# Kreiranje novog sećanja
omi memory create "Korisnik preferira tamnu temu u editoru." --category lifestyle

# Prikaz detalja određenog sećanja na osnovu ID-a
omi memory get <MEMORY_ID>
```

### Razgovori (Conversations)

Razgovori predstavljaju transkribovane i analizirane govorne ili tekstualne sesije.

```bash
# Prikaz poslednjih 5 razgovora
omi conversation list --limit 5

# Prikaz kompletnog razgovora uključujući transkript
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Akcione stavke (Action Items)

Zadaci i preuzete obaveze prepoznate tokom razgovora ili ručno kreirane:

```bash
# Prikaz samo otvorenih (nedovršenih) stavki
omi action-item list --open

# Ručno kreiranje nove akcione stavke
omi action-item create "Pripremiti pregled koda pre sastanka tima."

# Označavanje stavke kao završene
omi action-item complete <ACTION_ITEM_ID>
```

### Ciljevi (Goals)

Praćenje dugoročnih ciljeva i napretka:

```bash
# Prikaz svih ciljeva
omi goal list

# Evidentiranje napretka (potrebni su i ID cilja i numerička vrednost)
omi goal progress <GOAL_ID> 25

# Prikaz istorije promena i ažuriranja cilja
omi goal history <GOAL_ID>
```

---

## 4. Postavljanje pitanja prirodnim jezikom (`ask`)

`omi ask` je samostalna komanda najvišeg nivoa. Omogućava postavljanje pitanja na prirodnom jeziku, a odgovori se generišu na osnovu vaših zabeleženih razgovora i sećanja:

```bash
# Pitanje na prirodnom jeziku
omi ask "Šta smo odlučili u vezi sa selidbom kancelarije?"

# Pitanje sa strukturiranim JSON izlazom
omi --json ask "Koji su ključni zadaci koje treba završiti ove sedmice?"
```

---

## 5. JSON format i rad sa skriptama (`--json`)

`omi-cli` pruža kompletan strogo tipiziran JSON izlaz namenjen automatizaciji i obradi pomoću alata kao što je `jq`.

> **Pravilo pozicioniranja:** Zastavica `--json` je **globalna opcija** i mora se navesti **pre** potkomande:
> * **Ispravno:** `omi --json memory list`
> * **Neispravno:** `omi memory list --json` (izaziva grešku Click parsera)

U `--json` režimu, na standardni izlaz (`stdout`) se ispisuje isključivo validan JSON. Dijagnostičke poruke i greške se šalju na standardni izlaz za greške (`stderr`), što garantuje pouzdan rad cevovoda.

### Primeri filtriranja pomoću alata `jq`:

```bash
# Izdvajanje polja id, content i category iz svih sećanja
omi --json memory list | jq '.[] | {id, content, category}'

# Prikaz ID-a, naslova i vremena početka poslednjih 5 razgovora
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Prikaz otvorenih akcionih stavki
omi --json action-item list --open | jq '.'

# Paginacija: čuvanje prve stranice od 25 sećanja u lokalnu datoteku
omi --json memory list --limit 25 --offset 0 > secanja-strana-1.json

# Sledeća stranica
omi --json memory list --limit 25 --offset 25 > secanja-strana-2.json
```

---

## 6. Izlazni kodovi (Exit Codes)

`omi-cli` garantuje postojane i predvidive izlazne kodove (definisane u modulu `omi_cli/errors.py`), što omogućava pouzdano grananje u skriptama i CI tokovima:

| Kod | Konstanta | Kategorija | Značenje i postupak |
| :---: | :--- | :--- | :--- |
| **`0`** | `EXIT_OK` | Uspeh | Komanda je u potpunosti i uspešno izvršena. |
| **`1`** | `EXIT_USAGE` | Greška u upotrebi | Interna validaciona greška u `omi-cli` (npr. istovremeni izbor `--browser` i `--api-key`, neispravan metod prijave, prazan unos na stdin). |
| **`2`** | `EXIT_AUTH` | Greška autentifikacije | Korisnik nije prijavljen, API ključ je nevažeći ili je sesija istekla. *Napomena:* Click parser takođe vraća kod 2 kod nepoznatih opcija ili argumenata. |
| **`3`** | `EXIT_SERVER` | Serverska / Mrežna greška | HTTP 5xx odgovori, mrežni tajmaut ili prekid veze. |
| **`4`** | `EXIT_RATE_LIMITED` | Prekoračenje limita | HTTP 429 Too Many Requests. CLI automatski pokušava ponovo prateći zaglavlje `Retry-After`. |
| **`5`** | `EXIT_NOT_FOUND` | Resurs nije pronađen | HTTP 404 odgovor; traženi identifikator (ID) ne postoji. |

### Primer provere izlaznog koda u Bash skripti:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "Autentifikacija je ispravna."
else
  kod=$?
  case $kod in
    2) echo "Potrebna ponovna prijava: ključ je nevažeći ili nedostaje." ;;
    3) echo "Server je privremeno nedostupan. Pokušajte ponovo kasnije." ;;
    4) echo "Dostignut je limit zahteva." ;;
    *) echo "Došlo je do greške sa izlaznim kodom: $kod" ;;
  esac
fi
```

---

## 7. Promenljive okruženja

### Bash / Zsh (Linux, macOS)

```bash
# Postavljanje API ključa za tekuću sesiju
export OMI_API_KEY="omi_dev_vas_kljuc_ovde"

# Testiranje komande
omi --json memory list --limit 10
```

Za trajno postavljanje dodajte gornji `export` red u vašu konfiguraciju: `~/.bashrc` ili `~/.zshrc`.

### PowerShell (Windows)

```powershell
# Postavljanje za tekuću sesiju
$env:OMI_API_KEY = "omi_dev_vas_kljuc_ovde"

# Parsiranje JSON izlaza u PowerShell objektima
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Za trajno postavljanje na nivou korisnika:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_vas_kljuc_ovde", "User")
```

---

## 8. Lokalni Omi Desktop API

Ukoliko je Omi desktop aplikacija pokrenuta na vašem računaru, određene podatke i snimke ekrana možete očitavati lokalno, bez slanja upita u oblak:

```bash
# Podešavanje lokalnog API pristupa
omi local configure --url http://127.0.0.1:47778 --token vas_lokalni_token

# Alternativno, putem promenljivih okruženja:
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
export OMI_LOCAL_TOKEN="vas_lokalni_token"

# Provera dostupnosti lokalnog servisa
omi --json local status

# Pretraga istorije snimaka ekrana
omi --json local search-screen "plan pretplate" --days 7 --app Safari

# Čuvanje određenog snimka ekrana po ID-u
omi --json local screenshot 123 --output /tmp/omi-snimak.jpg

# Izvršavanje SQL upita nad lokalnom SQLite bazom
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Preporučeni redosled: prvo proverite status komandom `omi --json local status`, zatim istražite dostupne alate putem `omi local tools`, a potom izvršavajte ciljane upite.

---

## 9. Profili i konfiguracija

Kada koristite više naloga ili odvojena okruženja (npr. lični i poslovni nalog), možete ih razdvojiti putem profila:

```bash
# Prijava pod ličnim profilom
omi --profile personal auth login

# Prijava pod poslovnim profilom
omi --profile work auth login

# Izvršavanje komande u okviru određenog profila
omi --profile work memory list
```

Redosled određivanja aktivnog profila je:
1. Zastavica `--profile` (ili `-p`) ima najviši prioritet.
2. Promenljiva okruženja `OMI_PROFILE`.
3. Aktivni profil podešen u datoteci `~/.omi/config.toml`.
4. Podrazumevani profil `default`.

Pregled i izmena konfiguracije:

```bash
# Prikaz trenutne konfiguracije
omi config show

# Lokacija konfiguracione datoteke
omi config path

# Promena konfiguracionog parametra
omi config set api_base https://api.omi.me
```

---

## 10. Sledeći koraci

* [`agent_quickstart.md`](./agent_quickstart.md) — uputstvo za povezivanje `omi-cli` sa autonomnim AI agentima i LLM sistemima.
* [`shell_examples.sh`](./shell_examples.sh) — gotovi primeri i isečci koda za shell skripte.
* [Zvanična Omi dokumentacija](https://docs.omi.me/doc/developer/cli/introduction) — detaljna referenca svih podržanih komandi i parametara.
