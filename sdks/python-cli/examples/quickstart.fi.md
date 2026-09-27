# Ensiaskeleet omi-cli-työkalun kanssa

Tämä opas selittää ensimmäiset komennot suomeksi. Komentojen nimet ja ohjelman
viestit pysyvät englanninkielisinä. Tässä esitetyt kyselyesimerkit eivät muuta
muistojasi, keskustelujasi, tehtäviäsi tai tavoitteitasi.

## Ohjelman asennus

Vaatimukset: Python 3.10 tai uudempi versio ja Omi-tili.

Jos sinulla on `pipx` asennettuna:

```sh
pipx install omi-cli
omi --help
```

Vaihtoehtoisesti voit asentaa sen aktivoidussa Pythonin virtuaaliympäristössä
(virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Jos pääte ei löydä komentoa `omi`, varmista, että virtuaaliympäristö on aktivoitu
tai että hakemisto, johon `pipx` asentaa suoritettavat tiedostot, on `PATH`-muuttujassasi.

## Tilisi yhdistäminen

Käynnistä interaktiivinen avustaja:

```sh
omi auth login
```

Valitse kirjautuminen selaimen kautta tai vaihtoehto liittää Omi-kehittäjän
API-avain. Interaktiivinen syöttö piilottaa avaimen; vältä sen kirjoittamista
komentoon, joka jää päätteen historiaan.

Siirtyäksesi suoraan selaimeen:

```sh
omi auth login --browser
```

Kirjaudu sisään samalla tietokoneella, jolla pääte toimii: todennusvastaus
käyttää paikallista osoitetta. Seuraa näytöllä näkyviä ohjeita.

Tarkista sen jälkeen määritykset ja API-yhteys:

```sh
omi auth status
omi auth whoami
```

`status` näyttää paikallisen tilan ja piilottaa salaisuuden, mutta ei tarkista
sen voimassaoloa palvelimelta. `whoami` tekee todennetun pyynnön; jos se onnistuu,
se vahvistaa kirjautumistietojen toimivuuden ilman, että nimeäsi välttämättä näytetään.

Määritykset tallennetaan oletuksena tiedostoon `~/.omi/config.toml`. Älä jaa tätä
tiedostoa muille: se voi sisältää luottamukselliset kirjautumistietosi.

## Tietojesi tarkasteleminen

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Tyhjä luettelo voi yksinkertaisesti tarkoittaa, että kyselyä vastaavia kohteita
ei ole. Käytä ohjetta löytääksesi kunkin komennon suodattimet:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-tulosteen hakeminen ja sivuilla siirtyminen

Aseta globaali valitsin `--json` **ennen** komentoryhmää:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ensimmäinen komento pyytää ensimmäiset 25 muistoa; toinen, seuraavat 25. Yksi
sivu ei siis ole täydellinen varmuuskopio (backup). JSON-tuloste säilyttää
täydet tunnisteet, kun taas näytön taulukot voivat lyhentää niitä näyttämistä varten.

Sivun tallentaminen tiedostoon:

```sh
omi --json memory list --limit 25 --offset 0 > muistot-sivu-1.json
```

Tämä uudelleenohjaus luo tai korvaa paikallisen tiedoston. Varmista, että komento
suoritettiin onnistuneesti ennen sen sisällön käyttöä. Virheet kirjoitetaan
virhetulosteeseen (stderr); tyhjä tiedosto ei takaa, ettei tietoja ole. Viety
tiedosto voi sisältää henkilökohtaisia tietoja: pidä se yksityisenä.

## Uloskirjautuminen (Logout)

```sh
omi auth logout
```

Tämä komento poistaa paikallisesti tallennetut kirjautumistiedot. Voit kumota
avaimen palvelimelta tilisi kehittäjäavainten hallinnasta.

Katso muut komennot ja lisäasetukset [englanninkielisestä pääoppaasta](../README.md)
ja komennolla `omi --help`.
