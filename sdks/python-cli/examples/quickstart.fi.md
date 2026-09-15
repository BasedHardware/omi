# omi-cli-pikaopas (Finnish Quickstart)

> Käytännön opas Omin komentorivityökalun käyttöön suoraan päätteestä — suunniteltu kehittäjille ja autonomisille tekoälyagenteille.

`omi-cli` on [Omi](https://omi.me) -kehittäjärajapinnan virallinen komentorivityökalu. Sen avulla voit hallinnoida ja automatisoida järjestelmän neljää keskeistä tietorakennetta: muistoja (memories), keskusteluja (conversations), toimintokohteita (action items) ja tavoitteita (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Virallinen dokumentaatio:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Lähdekoodi:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Asennus

Riippuvuusristiriitojen välttämiseksi ja CLI-työkalun ajamiseksi eristetyssä ympäristössä suositellaan `pipx`-työkalun käyttöä:

```bash
# Suositus: eristetty asennus pipxillä
pipx install omi-cli

# Vaihtoehtoinen asennus tavallisella pipillä (esim. virtuaaliympäristössä)
pip install omi-cli
```

> **Tärkeä huomio: Paketin nimi vs. Komennon nimi**
> * PyPI-paketin virallinen nimi on **`omi-cli`** (`omi`-nimi kuuluu toiselle, riippumattomalle paketille).
> * Päätteessä suoritettava komento on suoraan **`omi`**.

Varmista asennuksen onnistuminen tarkistamalla versionumero ja ohjevalikko:

```bash
omi --version
omi --help
```

---

## 2. Tunnistautuminen (Authentication)

`omi-cli` tukee kahta pääasiallista tunnistautumistapaa:

| Menetelmä | Käyttötarkoitus | Esimerkkikomento |
| :--- | :--- | :--- |
| **Kehittäjän API-avain (`omi_dev_*`)** | Automaatio, CI/CD, palvelimet, tekoälyagentit | `omi auth login --api-key ...` tai `OMI_API_KEY` |
| **Selainpohjainen OAuth (Google/Apple)** | Paikalliset työkoneet ja henkilökohtainen käyttö | `omi auth login --browser` (Google) / `--provider apple` |

### Interaktiivinen kirjautuminen
Jos suoritat komennon ilman valitsimia, komentotulkki kysyy haluamasi menetelmän:

```bash
omi auth login
# 1) Browser — Google-kirjautuminen selaimen kautta (Apple-tilille käytä `--provider apple`)
# 2) API key — Liitä app.omi.me-hallinnasta luomasi kehittäjäavain
```

### Suora selainkirjautuminen
```bash
# Oletusarvoinen Google-kirjautuminen
omi auth login --browser

# Vaihtoehtoinen Apple-kirjautuminen
omi auth login --browser --provider apple
```

### Kehittäjän API-avaimen käyttö
Luo API-avain [app.omi.me](https://app.omi.me) -hallintapaneelin kohdasta **Developer → API Keys**:

```bash
# Tallenna avain paikalliseen profiiliin
omi auth login --api-key omi_dev_...

# Tai aseta se ympäristömuuttujana (ihanteellinen konteissa ja CI/CD-putkissa)
# Huomautus: Jos aktiivisessa profiilissa on jo tallennettu avain, suorita ensin `omi auth logout`.
export OMI_API_KEY="omi_dev_oman_avaimesi_tahan"
```

### Tunnistautumisen tilan tarkistaminen
* `omi auth status`: Näyttää aktiivisen profiilin ja peitetyn tunnistetiedon; vanhentumisaika näkyy vain OAuth-profiileissa (toimii ilman verkkoyhteyttä).
* `omi auth whoami`: Lähettää todennetun pyynnön Omi-palvelimelle ja vahvistaa avaimen kelvollisuuden (vaatii verkkoyhteyden).

```bash
omi auth status
omi auth whoami
```

### Uloskirjautuminen (Logout)
```bash
omi auth logout
# Jos käytät OMI_API_KEY-ympäristömuuttujaa, poista se myös istunnosta (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Peruskomennot

### Muistot (Memories)
Omin tallentamat kontekstitiedot ja havainnot:

```bash
# Listaa tallennetut muistot
omi memory list

# Luo uusi muisto
omi memory create "Suosii teknisiä ja tiiviitä vastauksia Python-esimerkein" --category work

# Hae tietyn muiston tiedot
omi memory get <MEMORY_ID>
```

### Keskustelut (Conversations)
Omi-laitteiden tallentamat keskustelut ja litteroinnit:

```bash
# Listaa 5 viimeisintä keskustelua
omi conversation list --limit 5

# Hae keskustelun tiedot ja täysi litterointi
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Toimintokohteet ja tehtävät (Action Items)
Keskusteluista automaattisesti tunnistetut tehtävät:

```bash
# Listaa avoimet tehtävät
omi action-item list --open

# Merkitse tehtävä suoritetuksi
omi action-item complete <ACTION_ITEM_ID>
```

### Tavoitteet (Goals)
Pitkän aikavälin tavoitteet ja edistymisen seuranta:

```bash
# Listaa aktiiviset tavoitteet
omi goal list

# Luo uusi numeerinen tavoite
omi goal create "Juo 2 litraa vettä päivässä" --type numeric --target 2 --unit liters
```

---

## 4. Rakenteinen automaatio ja JSON-tuloste (`--json`)

`omi-cli` on suunniteltu saumattomaan skriptaukseen. Yleinen `--json`-lippu muotoilee tulosteet standardiksi JSON-rakenteeksi:

```bash
# Hae muistot JSON-muodossa ja suodata kentät jq-työkalulla
omi --json memory list | jq '.[] | {id, content, category}'

# Hae uusimpien keskustelujen otsikot
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Tarkastele avoimia tehtäviä raakana JSON-datana
omi --json action-item list --open | jq '.'
```

> **Tärkeä syntaksisääntö:**
> `--json`-lippu on **yleinen valitsin**, ja sen täytyy sijaita **ennen** alikomentoa:
> * Oikein: `omi --json memory list`
> * Väärin: `omi memory list --json`

### Sivutus ja vienti tiedostoon
Käytä `--limit`- ja `--offset`-valitsimia suurten tietomäärien selaamiseen:

```bash
# Sivuta tuloksia
omi --json memory list --limit 25 --offset 0 > muistot-sivu-1.json
omi --json memory list --limit 25 --offset 25 > muistot-sivu-2.json
```

Tiedostoon ohjaus luo tai ylikirjoittaa tiedoston. Varmista aina komennon onnistuminen poistumiskoodin avulla. Virheet tulostuvat vakiovirhevirtaan (stderr), joten tyhjä tiedosto ei takaa datan puuttumista. Viety data voi sisältää henkilökohtaisia tietoja — säilytä tiedostot turvallisesti.

---

## 5. Poistumiskoodit (Exit Codes)

Luotettava virheenkäsittely komentosarjoissa ja CI/CD-ympäristöissä:

| Koodi | Merkitys | Selite |
| :---: | :--- | :--- |
| `0` | **Onnistuminen (`EXIT_OK`)** | Toiminto suoritettiin virheettömästi. |
| `1` | **Käyttövirhe / Syntaksi (`EXIT_USAGE`)** | Virheelliset valitsimet, puuttuvat argumentit tai sovellustason validointivirhe. |
| `2` | **Tunnistautumisvirhe (`EXIT_AUTH`)** | Puuttuvat tunnistetiedot, vanhentunut avain tai riittämättömät käyttöoikeudet. |
| `3` | **Palvelin- tai verkkovirhe (`EXIT_SERVER`)** | HTTP 5xx -vastaus, aikakatkaisu tai yhteysongelma palvelimeen. |
| `4` | **Pyyntöjen määrärajoitus (`EXIT_RATE_LIMITED`)** | HTTP 429 -vastaus — liian monta pyyntöä lyhyessä ajassa. |
| `5` | **Ei löydy (`EXIT_NOT_FOUND`)** | HTTP 404 -vastaus — pyydettyä resurssia ei ole olemassa. |

---

## 6. Komentosarjaesimerkit eri ympäristöissä

### Bash / Zsh (Linux / macOS)
```bash
export OMI_API_KEY="omi_dev_oman_avaimesi_tahan"

# Suorita komento ja tarkista poistumiskoodi
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Virhe haettaessa muistoja." >&2
fi
```

### PowerShell (Windows)
```powershell
$env:OMI_API_KEY = "omi_dev_oman_avaimesi_tahan"

# Muunna JSON-tuloste suoraan PowerShell-objektiksi
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Tarkista poistumiskoodi muuttujasta $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Omi-komento epäonnistui koodilla $LASTEXITCODE."
}
```

---

## 7. Paikallisen työpöytäsovelluksen rajapinta (Local Desktop API)

Kun Omi Desktop -sovellus on käynnissä tietokoneellasi, voit tehdä hakuja paikallisesta ruutu- ja kontekstihistoriasta ilman pilvikutsuja:

```bash
# Määritä paikallinen päätepiste ja aseta tunnistetieto
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Tarkista paikallisen palvelun tila
omi --json local status

# Tee haku viimeisimmältä visuaaliselta aikajanalta
omi --json local search-screen "Neljännesvuosiraportti" --days 7 --app Safari
```

---

## 8. Usean profiilin hallinta (Profiles)

Voit erottaa henkilökohtaisen tilin, työtilin tai testausympäristöt toisistaan `--profile`-valitsimen avulla. Asetukset tallennetaan tiedostoon `~/.omi/config.toml`:

```bash
# Luo henkilökohtainen profiili ja kirjaudu sisään
omi --profile personal auth login

# Luo työprofiili ja kirjaudu sisään
omi --profile work auth login

# Suorita komentoja tietyllä profiililla
omi --profile work memory list

# Käytä erillistä testiympäristöä
omi --profile staging --api-base https://api.staging.omi.me memory list
```

---

## 9. Tietoturva ja parhaat käytännöt

* **Älä tallenna avaimia Git-versionhallintaan:** Älä koskaan vie API-avaimia julkisiin tietovarastoihin; käytä salaisuuksien hallintaa tai `.gitignore`-tiedostolla suojattuja ympäristötiedostoja.
* **Komentohistorian suojaaminen:** Vältä avaimien kirjoittamista suoraan komentoriville jaetuilla koneilla; käytä mieluummin interaktiivista syöttöä tai `OMI_API_KEY`-ympäristömuuttujaa.
* **Hakemiston käyttöoikeudet:** Rajoita Unix-pohjaisissa järjestelmissä `~/.omi/`-asetushakemiston luku- ja kirjoitusoikeudet vain omalle käyttäjällesi (`chmod 700 ~/.omi`).
