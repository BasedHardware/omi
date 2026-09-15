# omi-cli — brzi vodič na hrvatskom

> Praktičan vodič za rad s Omijem iz terminala. Odgovara i čovjeku i AI agentu.

`omi-cli` je službeno sučelje naredbenog retka za razvojni API [Omija](https://omi.me).
Pruža brz i skriptabilan pristup četirima glavnim entitetima Omija:
sjećanjima (memories), razgovorima (conversations), zadacima (action items) i ciljevima (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorni kod:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacija

Preporučeni način je `pipx`: instalira alat u izolirano okruženje,
pa se njegove ovisnosti ne sudaraju s vašim projektima.

```bash
# preporučeno: instalacija preko pipx-a
pipx install omi-cli

# ili preko pip-a
pip install omi-cli
```

> **Važno: naziv paketa i naziv naredbe se razlikuju.**
> * Instalira se paket **`omi-cli`** (zaseban paket `omi` je drugi, nepovezani projekt).
> * Nakon instalacije pokreće se naredba **`omi`**.

Provjerite da je instalacija uspjela:

```bash
omi --version
omi --help
```

---

## 2. Prijava

`omi-cli` podržava dva načina prijave.

| Način | Kada odgovara | Naredba |
| :--- | :--- | :--- |
| **Razvojni ključ (`omi_dev_*`)** | CI/CD, skripte, AI agenti | `omi auth login --api-key ...` ili varijabla okruženja |
| **Prijava kroz preglednik (Google/Apple)** | Rad na vlastitom računalu | `omi auth login --browser` |

### Interaktivna prijava

Bez zastavica naredba sama pita kojim načinom se želite prijaviti:

```bash
omi auth login
# 1) Browser — prijava kroz Google ili Apple (praktično za čovjeka)
# 2) API key — zalijepite razvojni ključ s app.omi.me (praktično za agente i CI)
```

Kad odaberete ključ, unos se maskira pa ključ ne ostaje u povijesti terminala.

### Izravno kroz preglednik

```bash
omi auth login --browser
```

### Pomoću razvojnog ključa

Ključ se uzima na [app.omi.me](https://app.omi.me) u odjeljku **Developer → API Keys**.

```bash
# spremiti ključ u konfiguraciju
omi auth login --api-key omi_dev_...

# ili ga proslijediti kroz okruženje — poželjno za CI/CD i kontejnere
export OMI_API_KEY=omi_dev_...
```

Varijabla `OMI_API_KEY` koristi se kad aktivni profil nema spremljen ključ,
pa u kontejneru ništa ne trebate pisati na disk. Ako u profilu već postoji
ključ, on ima prednost nad varijablom okruženja.

### Provjera prijave

Dvije naredbe odgovaraju na različita pitanja i ne treba ih miješati:

* `omi auth status` — što je spremljeno **lokalno**: profil, maskirani ključ, valjanost.
  Radi bez mreže.
* `omi auth whoami` — upit **prema poslužitelju Omija**: provjerava prihvaća li
  poslužitelj ključ. Zahtijeva mrežu.

```bash
omi auth status    # lokalna provjera, izvanmrežno
omi auth whoami    # provjera na poslužitelju
```

Obnovite OAuth sesiju kojoj ističe valjanost bez ponovne prijave — vrijedi samo za prijavu u pregledniku (OAuth). Za ključeve `omi_dev_*` ova naredba ne obnavlja; zamijenite ključ u web-aplikaciji pod `Developer → API Keys`:

```bash
omi auth refresh
```

Odjava:

```bash
omi auth logout
```

---

## 3. Osnovne naredbe

### Sjećanja (memories)

Činjenice i znanja koja je sustav zapamtio o vama.

```bash
# popis sjećanja
omi memory list

# stvoriti novo
omi memory create "Korisnik preferira tamnu temu" --category lifestyle

# pogledati konkretno
omi memory get <MEMORY_ID>
```

### Razgovori (conversations)

Povijest govora i teksta s uređaja ili iz aplikacije.

```bash
# zadnjih 5 razgovora
omi conversation list --limit 5

# cijeli razgovor s transkriptom
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Zadaci (action items)

Zadaci koje je Omi izdvojio iz razgovora.

```bash
# samo nedovršeni
omi action-item list --open

# označiti kao dovršen
omi action-item complete <ACTION_ITEM_ID>
```

### Ciljevi (goals)

```bash
# popis ciljeva
omi goal list

# zapisati novu vrijednost napretka (potrebna su OBA argumenta: cilj i vrijednost)
omi goal progress <GOAL_ID> 25

# povijest promjena
omi goal history <GOAL_ID>
```

---

## Pitanje vlastitim riječima (`ask`)

Zasebna naredba najviše razine: postavlja pitanje prirodnim jezikom,
a odgovor se gradi iz vaših vlastitih razgovora.

```bash
omi ask "što sam odlučio o selidbi"
omi --json ask "koje sam zadatke obećao završiti ovaj tjedan"
```

---

## 4. JSON i skripte (`--json`)

`omi-cli` može vratiti strojno čitljiv JSON. Zastavica `--json` je **globalna**,
pa se stavlja **prije** podnaredbe.

```bash
# sjećanja: izvući id, tekst i kategoriju
omi --json memory list | jq '.[] | {id, content, category}'

# naslovi zadnjih razgovora
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# nedovršeni zadaci
omi --json action-item list --open | jq '.'
```

> **Česta pogreška.** `--json` ide prije podnaredbe, a ne poslije.
> * Točno: `omi --json memory list`
> * Netočno: `omi memory list --json`

U načinu `--json` na standardni izlaz ne dolazi ništa osim samog JSON-a —
na to se možete osloniti u skriptama.

---

## 5. Izlazni kodovi

Kodovi su stabilni, pa se po njima može granati logika u skriptama i CI-ju.

| Kod | Značenje | Kada nastupa |
| :---: | :--- | :--- |
| `0` | Uspjeh | Naredba je završila |
| `1` | Greška u pozivu | Vlastita provjera omi-clija (npr. `--browser` i `--api-key` zajedno, nevažeći izbor, prazan unos) |
| `2` | Greška u pristupu ili argumentima | Niste prijavljeni, ključ je neispravan ili istekao — uključuje i greške parsera (nepoznata zastavica, nedostajući argument) |
| `3` | Greška poslužitelja | Odgovor 5xx, timeout, nema veze |
| `4` | Previše zahtjeva | 429 Too Many Requests |
| `5` | Nije pronađeno | 404, navedeni identifikator ne postoji |

Primjer provjere u Bashu:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "ključ radi"
else
  code=$?
  [ "$code" -eq 2 ] && echo "potrebna je ponovna prijava"
  [ "$code" -eq 3 ] && echo "poslužitelj nedostupan, pokušajte kasnije"
fi
```

---

## 6. Varijable okruženja

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_vas_kljuc"

omi --json memory list --limit 10
```

Da bi se ključ učitavao u novim sesijama, dodajte redak u `~/.bashrc` ili `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_vas_kljuc"

# obrada JSON-a pomoću PowerShella
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Trajna postavka:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_vas_kljuc", "User")
```

---

## 7. Lokalna aplikacija Omi Desktop

Ako je pokrenuta desktop aplikacija Omi, dio podataka dostupan je izravno,
bez zaobilaska preko oblaka.

```bash
# postaviti adresu lokalnog API-ja
omi local configure --url http://127.0.0.1:47778 --token VAS_TOKEN

# provjeriti da odgovara
omi --json local status

# pretraga povijesti zaslona
omi --json local search-screen "tarife" --days 7 --app Safari

# snimka zaslona prema identifikatoru
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# proizvoljni SQL upit nad lokalnom bazom
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Redoslijed rada: prvo `local status`, zatim `local tools` — kako biste saznali
dostupne alate i njihove parametre — i tek onda pozivi.

---

## 8. Profili

Ako imate više računa ili okruženja, razdvojite ih profilima.
Postavke se čuvaju u `~/.omi/config.toml`.

```bash
# prijava u osobni profil
omi --profile personal auth login

# prijava u poslovni
omi --profile work auth login

# izvršiti naredbu u konkretnom profilu
omi --profile work memory list
```

Ako ne navedete profil, CLI prvo koristi profil iz varijable okruženja `OMI_PROFILE`, zatim aktivni profil iz konfiguracijske datoteke, pa `default`. Redoslijed prednosti: `--profile` → `OMI_PROFILE` → aktivni profil u `~/.omi/config.toml` → `default`.

Pogledati i mijenjati samu konfiguraciju:

```bash
# što je trenutačno postavljeno
omi config show

# gdje se nalazi konfiguracijska datoteka
omi config path

# promijeniti vrijednost
omi config set api_base https://api.omi.me
```

---

## 9. Što dalje

* [`agent_quickstart.md`](./agent_quickstart.md) — kako povezati `omi-cli` s AI agentom.
* [`shell_examples.sh`](./shell_examples.sh) — gotovi primjeri za ljusku.
* [Dokumentacija Omija](https://docs.omi.me/doc/developer/cli/introduction) — potpuni pregled naredbi.
