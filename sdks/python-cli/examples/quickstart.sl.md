# omi-cli — hitri začetek v slovenščini

> Praktičen vodnik za delo z Omijem iz terminala. Primeren za človeka in za AI agenta.

`omi-cli` je uradni vmesnik ukazne vrstice za razvijalski API [Omija](https://omi.me).
Omogoča hiter in skriptibilen dostop do štirih glavnih entitet Omija:
spominov (memories), pogovorov (conversations), nalog (action items) in ciljev (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentacija:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Izvorna koda:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Namestitev

Priporočen način je `pipx`: orodje namesti v izolirano okolje,
zato se njegove odvisnosti ne spopadajo z vašimi projekti.

```bash
# priporočeno: namestitev prek pipx
pipx install omi-cli

# ali prek pip
pip install omi-cli
```

> **Pomembno: ime paketa in ime ukaza se razlikujeta.**
> * Namesti se paket **`omi-cli`** (samostojni paket `omi` je drug, nepovezan projekt).
> * Po namestitvi se zažene ukaz **`omi`**.

Preverite, da je namestitev uspela:

```bash
omi --version
omi --help
```

---

## 2. Prijava

`omi-cli` podpira dva načina prijave.

| Način | Kdaj je primeren | Ukaz |
| :--- | :--- | :--- |
| **Razvijalski ključ (`omi_dev_*`)** | CI/CD, skripte, AI agenti | `omi auth login --api-key ...` ali okoljska spremenljivka |
| **Prijava prek brskalnika (Google/Apple)** | Delo na svojem računalu | `omi auth login --browser` |

### Interaktivna prijava

Brez zastavic ukaz sam vpraša, na kateri način se želite prijaviti:

```bash
omi auth login
# 1) Browser — prijava prek Googla ali Appla (prikladno za človeka)
# 2) API key — prilepite razvijalski ključ z app.omi.me (prikladno za agente in CI)
```

Pri izbiri ključa se vnos maskira, zato ključ ne ostane v zgodovini terminala.

### Neposredno prek brskalnika

```bash
omi auth login --browser
```

### Z razvijalskim ključem

Ključ dobite na [app.omi.me](https://app.omi.me) v razdelku **Developer → API Keys**.

```bash
# shraniti ključ v konfiguracijo
omi auth login --api-key omi_dev_...

# ali ga posredovati prek okolja — bolje za CI/CD in vsebnike
export OMI_API_KEY=omi_dev_...
```

Spremenljivka `OMI_API_KEY` se uporabi, kadar aktivni profil nima shranjenega ključa,
zato v vsebniku ni treba ničesar pisati na disk. Če je ključ v profilu že
shranjen, ima prednost pred okoljsko spremenljivko.

### Preverjanje prijave

Dva ukaza odgovarjata na različni vprašanji in ju ne smete zamenjevati:

* `omi auth status` — kaj je shranjeno **lokalno**: profil, maskiran ključ, veljavnost.
  Deluje brez omrežja.
* `omi auth whoami` — povpraševanje **Omijevega strežnika**: preveri, ali strežnik
  ključ resnično sprejme. Zahteva omrežje.

```bash
omi auth status    # lokalno preverjanje, brez povezave
omi auth whoami    # preverjanje na strežniku
```

Obnovitev ključa s potečeno veljavnostjo brez ponovne prijave:

```bash
omi auth refresh
```

Odjava:

```bash
omi auth logout
```

---

## 3. Osnovni ukazi

### Spomini (memories)

Dejstva in znanja, ki si jih je sistem zapomnil o vas.

```bash
# seznam spominov
omi memory list

# ustvariti novega
omi memory create "Uporabnik ima raje temno temo" --category lifestyle

# ogled konkretnega
omi memory get <MEMORY_ID>
```

### Pogovori (conversations)

Zgodovina govora in besedila z naprave ali iz aplikacije.

```bash
# zadnjih 5 pogovorov
omi conversation list --limit 5

# celoten pogovor s prepisom
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Naloge (action items)

Naloge, ki jih je Omi izluščil iz pogovorov.

```bash
# samo nedokončane
omi action-item list --open

# označiti kot dokončano
omi action-item complete <ACTION_ITEM_ID>
```

### Cilji (goals)

```bash
# seznam ciljev
omi goal list

# zapisati novo vrednost napredka (potrebna sta OBA argumenta: cilj in vrednost)
omi goal progress <GOAL_ID> 25

# zgodovina sprememb
omi goal history <GOAL_ID>
```

---

## Vprašanje v svojih besedah (`ask`)

Samostojni ukaz najvišje ravni: postavi vprašanje v naravnem jeziku,
odgovor pa se sestavi iz vaših lastnih pogovorov.

```bash
omi ask "kaj sem se odločil glede selitve"
omi --json ask "katere naloge sem obljubil zaključiti ta teden"
```

---

## 4. JSON in skripte (`--json`)

`omi-cli` zna vrniti strojno berljiv JSON. Zastavica `--json` je **globalna**,
zato jo podajte **pred** podukazom.

```bash
# spomini: izvleči id, besedilo in kategorijo
omi --json memory list | jq '.[] | {id, content, category}'

# naslovi zadnjih pogovorov
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# nedokončane naloge
omi --json action-item list --open | jq '.'
```

> **Pogosta napaka.** `--json` gre pred podukaz, ne za njim.
> * Pravilno: `omi --json memory list`
> * Napačno: `omi memory list --json`

V načinu `--json` na standardni izhod ne pride nič drugega kot sam JSON —
na to se lahko zanesete v skriptah.

---

## 5. Izhodne kode

Kode so stabilne, zato se po njih lahko veji logika v skriptah in CI.

| Koda | Pomen | Kdaj nastane |
| :---: | :--- | :--- |
| `0` | Uspeh | Ukaz se je izvedel |
| `1` | Napaka klica | Neveljavna zastavica, manjka argument |
| `2` | Napaka dostopa | Niste prijavljeni, ključ je neveljaven ali potekel |
| `3` | Napaka strežnika | Odgovor 5xx, timeout, ni povezave |
| `4` | Preveč zahtevkov | 429 Too Many Requests |
| `5` | Ni najdeno | 404, navedeni identifikator ne obstaja |

Primer preverjanja v Bashu:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "ključ deluje"
else
  code=$?
  [ "$code" -eq 2 ] && echo "potrebna je ponovna prijava"
  [ "$code" -eq 3 ] && echo "strežnik nedostopen, poskusite pozneje"
fi
```

---

## 6. Okoljske spremenljivke

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_vas_kljuc"

omi --json memory list --limit 10
```

Da se ključ naloži tudi v novih sejah, dodajte vrstico v `~/.bashrc` ali `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_vas_kljuc"

# obdelava JSON s PowerShellom
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Trajna nastavitev:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_vas_kljuc", "User")
```

---

## 7. Lokalna aplikacija Omi Desktop

Če teče namizna aplikacija Omi, je del podatkov dostopen neposredno,
brez obiska oblaka.

```bash
# nastaviti naslov lokalnega API-ja
omi local configure --url http://127.0.0.1:47778 --token VAS_ZETON

# preveriti, ali odgovarja
omi --json local status

# iskanje po zgodovini zaslona
omi --json local search-screen "tarife" --days 7 --app Safari

# posnetek zaslona po identifikatorju
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# poljubna SQL poizvedba nad lokalno bazo
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Vrstni red dela: najprej `local status`, nato `local tools` — da izveste
razpoložljiva orodja in njihove parametre — in šele nato klici.

---

## 8. Profili

Če imate več računov ali okolij, jih ločite po profilih.
Nastavitve se hranijo v `~/.omi/config.toml`.

```bash
# prijava v osebni profil
omi --profile personal auth login

# prijava v službenega
omi --profile work auth login

# izvesti ukaz v konkretnem profilu
omi --profile work memory list
```

Ogled in spreminjanje same konfiguracije:

```bash
# kaj je trenutno nastavljeno
omi config show

# kje leži konfiguracijska datoteka
omi config path

# spremeniti vrednost
omi config set api_base https://api.omi.me
```

---

## 9. Kaj naprej

* [`agent_quickstart.md`](./agent_quickstart.md) — kako povezati `omi-cli` z AI agentom.
* [`shell_examples.sh`](./shell_examples.sh) — pripravljeni primeri za lupino.
* [Dokumentacija Omija](https://docs.omi.me/doc/developer/cli/introduction) — popoln pregled ukazov.
