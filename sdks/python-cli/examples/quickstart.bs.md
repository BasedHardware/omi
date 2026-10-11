# Vodič za brzi početak rada s omi-cli (Bosnian Quickstart)

> Praktičan vodič za interakciju s Omijem direktno iz terminala — dizajniran za programere i autonomne AI agente.

`omi-cli` je zvanični interfejs komandne linije (CLI) za programerski API servisa [Omi](https://omi.me). Pruža strukturiran i agentima prilagođen pristup četirima osnovnim resursima: **sjećanjima** (memories), **razgovorima** (conversations), **akcionim stavkama** (action items) i **ciljevima** (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Zvanična dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorni kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacija

Kako biste spriječili konflikte među paketima i zadržali čisto okruženje, preporučuje se korištenje alata `pipx`:

```bash
# Preporučena metoda: izolovana instalacija putem pipx-a
pipx install omi-cli

# Alternativna instalacija putem standardnog pip-a (npr. u virtuelnom okruženju)
pip install omi-cli
```

> **Važna razlika: Naziv paketa vs. Naziv naredbe**
> * Naziv paketa pri instalaciji je **`omi-cli`**.
> * Izvršna naredba u terminalu je **`omi`**.

Provjerite ispravnost instalacije:

```bash
omi --version
```

---

## 2. Autentifikacija

`omi-cli` podržava dvije glavne metode autentifikacije: **OAuth putem pretraživača** (za interaktivne korisnike) i **Programerske API ključeve** (za automatizaciju i AI agente).

### Metoda A: Prijava putem pretraživača (Korisnici)

Podrazumijevana metoda prijave koristi Google nalog:

```bash
omi auth login
```

Ili se prijavite koristeći Apple ID:

```bash
omi auth login --provider apple
```

Ova komanda otvara prozor web pretraživača radi potvrde identiteta i sprema pristupni token u konfiguracijsku datoteku `~/.omi/config.toml`.

### Metoda B: Programerski API ključ (Skripte i Agenti)

Za pozadinske servise, CI/CD procese ili autonomne agente, koristite programerski API ključ (`omi_dev_*`):

```bash
# Opcija 1: Postavljanje varijable okruženja (najbolja praksa za kontejnere i servere)
export OMI_API_KEY="omi_dev_vas_kljuc_ovdje"

# Opcija 2: Prijava i trajno spremanje u lokalnu konfiguraciju
omi auth login --api-key "omi_dev_vas_kljuc_ovdje"
```

### Provjera statusa autentifikacije

Na raspolaganju su dvije komande za provjeru statusa:

```bash
# Lokalna provjera bez pristupa mreži (čita konfiguraciju ili varijable okruženja)
omi auth status

# Aktivna provjera na serveru (potvrđuje validnost sesije i dohvaća profil)
omi auth whoami
```

### Odjava

Za brisanje sačuvanih pristupnih podataka s lokalnog sistema:

```bash
omi auth logout
```

---

## 3. Upravljanje sjećanjima (Memories)

Sjećanja predstavljaju pojedinačne zabilješke i kontekstualne činjenice koje Omi pamti za vas.

```bash
# Prikaz najnovijih sjećanja (podrazumijevano 25 stavki)
omi memory list

# Ograničavanje broja prikazanih sjećanja
omi memory list --limit 10

# Paginacija (preskakanje početnih stavki)
omi memory list --limit 10 --offset 20

# Dohvatanje detalja određenog sjećanja putem ID-a
omi memory get <memory-id>

# Ručno kreiranje novog sjećanja
omi memory create "Omiljeni programski jezik tima je Python."
```

---

## 4. Razgovori, akcione stavke i ciljevi

### Razgovori (Conversations)

```bash
# Prikaz liste nedavnih razgovora
omi conversation list

# Dohvatanje detalja i transkripta specifičnog razgovora
omi conversation get <conversation-id>
```

### Akcione stavke (Action Items)

Zadaci ili obaveze prepoznate tokom razgovora ili ručno dodate:

```bash
# Prikaz otvorenih akcionih stavki
omi action-item list

# Kreiranje nove akcione stavke
omi action-item create "Pripremiti sažetak i pregled koda prije sastanka."
```

### Ciljevi (Goals)

Dugoročni ciljevi i planovi koje pratite:

```bash
# Prikaz svih aktivnih ciljeva
omi goal list

# Kreiranje novog cilja
omi goal create "Završiti integraciju Omi CLI alata do kraja kvartala."
```

---

## 5. JSON format i integracija cjevovoda (jq)

Za integraciju s automatizovanim skriptama i AI agentima koristite globalnu zastavicu `--json`.

> **Važno pravilo:** Zastavica `--json` mora se navesti **prije** glagola ili podkomande:

```bash
# Ispravno:
omi --json memory list

# Neispravno (rezultirat će greškom Click parsera):
omi memory list --json
```

### Primjeri filtriranja pomoću alata `jq`:

```bash
# Izdvajanje samo identifikatora (ID) svih sjećanja
omi --json memory list | jq -r '.[].id'

# Izdvajanje sadržaja sjećanja kao pojedinačnih linija teksta
omi --json memory list | jq -r '.[].content'

# Prikaz ID-a i naslova razgovora u sažetom formatu
omi --json conversation list | jq -r '.[] | "\(.id): \(.structured.title)"'

# Brojanje ukupnog broja otvorenih akcionih stavki
omi --json action-item list | jq 'length'
```

---

## 6. Izlazni kodovi i obrada grešaka

`omi-cli` implementira stroge ugovore o izlaznim kodovima definisane u `omi_cli/errors.py`:

| Kod | Konstanta | Kategorija | Značenje i postupak |
| :---: | :--- | :--- | :--- |
| **`0`** | `EXIT_OK` | Uspjeh | Naredba je uspješno i potpuno izvršena. |
| **`1`** | `EXIT_USAGE` | Pogrešna upotreba | Interna validacijska greška unutar `omi-cli` (npr. istovremeno zadavanje `--browser` i `--api-key`). *Napomena:* Standardne greške Click parsera (poput nepoznate zastavice) vraćaju kod **2**. |
| **`2`** | `EXIT_AUTH` | Autentifikacija | Nedostaje token, nevažeći API ključ ili je sesija istekla. Također se javlja kod grešaka Click parsera. |
| **`3`** | `EXIT_SERVER` | Serverska / Mrežna greška | HTTP 5xx odgovor ili prekid mrežne veze. Nije garantovano da li je operacija upisa izvršena na serveru. |
| **`4`** | `EXIT_RATE_LIMITED` | Prekoračenje limita | HTTP 429 odgovor. CLI automatski ponavlja zahtjev poštujući zaglavlje `Retry-After`. |
| **`5`** | `EXIT_NOT_FOUND` | Nije pronađeno | HTTP 404 odgovor. Navedeni resurs ili ID ne postoji ili je uklonjen. |

> **Osvježavanje pristupnog tokena:** Naredba `omi auth refresh` namijenjena je isključivo sesijama pretraživača (OAuth). Za programerske API ključeve ova naredba vraća grešku (izlazni kod 1) jer nema tokena za osvježavanje.

---

## 7. Primjeri skripti za automatizaciju

### Bash skripta: Kreiranje sjećanja s provjerom izlaznih kodova

```bash
#!/usr/bin/env bash
set -euo pipefail

TEKST="Sastanak tima je zakazan za ponedjeljak u 10:00 sati."

echo "Kreiranje novog sjećanja..."
if ODGOVOR=$(omi --json memory create "$TEKST" 2>&1); then
  MEMORY_ID=$(echo "$ODGOVOR" | jq -r '.id // empty')
  echo "Uspjeh! ID novog sjećanja: $MEMORY_ID"
else
  STATUS=$?
  echo "Greška pri kreiranju sjećanja (Izlazni kod: $STATUS)"
  case $STATUS in
    2) echo "Autentifikacijska greška: Provjerite OMI_API_KEY ili pokrenite 'omi auth login'." ;;
    3) echo "Serverska ili mrežna greška. Pokušajte ponovo kasnije." ;;
    4) echo "Prekoračen je limit dozvoljenih zahtjeva." ;;
    *) echo "Došlo je do greške: $ODGOVOR" ;;
  esac
  exit $STATUS
fi
```

### PowerShell skripta: Pregled akcionih stavki

```powershell
$odgovor = omi --json action-item list | ConvertFrom-Json

foreach ($stavka in $odgovor) {
    [PSCustomObject]@{
        Id        = $stavka.id
        Sadrzaj   = $stavka.content
        Kreirano  = $stavka.created_at
    }
}
```

---

## 8. Napredne mogućnosti

### Povezivanje s lokalnim Desktop API-jem

Ako je Omi desktop aplikacija pokrenuta na vašem lokalnom računaru, `omi-cli` može direktno komunicirati s njom putem porta `47778` bez potrebe za slanjem podataka u oblak:

```bash
# Konfiguracija varijabli okruženja za lokalni API
export OMI_LOCAL_API_URL="http://localhost:47778"
export OMI_LOCAL_TOKEN="vas_lokalni_sigurnosni_token"

# Izvršavanje naredbi prema lokalnom servisu
omi memory list
```

### Upravljanje profilima i testnim okruženjem (Staging)

Zastavica `--profile` omogućava rad s više odvojenih konfiguracija (npr. privatni nalog, posao ili testno okruženje). Konfiguracija se čuva u `~/.omi/config.toml`:

```bash
# Prijava na različite profile
omi --profile privatno auth login
omi --profile posao auth login

# Izvršavanje komandi pod određenim profilom
omi --profile posao memory list

# Rad s testnim (staging) okruženjem
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Sigurnost i najbolje prakse

* **Čuvanje tajnih ključeva:** Nikada nemojte pohranjivati `omi_dev_*` ključeve u javna Git skladišta koda. Uvijek koristite varijable okruženja ili sigurne sisteme za upravljanje tajnama.
* **Dozvole nad datotekama (Unix):** Zaštitite konfiguracijski direktorij odgovarajućim restriktivnim dozvolama:
  ```bash
  chmod 700 ~/.omi
  ```
* **Čišćenje privremenih sesija:** Na dijeljenim mašinama ili privremenim radnim stanicama, uklonite podatke nakon završetka rada:
  ```bash
  unset OMI_API_KEY
  omi auth logout
  ```
