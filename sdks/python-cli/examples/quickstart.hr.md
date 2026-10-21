# Prvi koraci s omi-cli

Ovaj vodič objašnjava prve naredbe na hrvatskom jeziku. Nazivi naredbi i poruke
programa ostaju na engleskom jeziku. Primjeri upita prikazani ovdje ne mijenjaju
vaša sjećanja, razgovore, zadatke niti ciljeve.

## Instalacija programa

Zahtjevi: Python 3.10 ili novija verzija i Omi račun.

Ako imate instaliran `pipx`:

```sh
pipx install omi-cli
omi --help
```

Alternativno, možete ga instalirati unutar aktiviranog Python virtualnog okruženja:

```sh
python -m pip install omi-cli
omi --help
```

Ako terminal ne pronađe `omi`, provjerite je li virtualno okruženje aktivirano
ili se direktorij u koji `pipx` instalira izvršne datoteke nalazi u vašem `PATH`-u.

## Povezivanje vašeg računa

Pokrenite interaktivnog asistenta:

```sh
omi auth login
```

Odaberite prijavu putem preglednika ili opciju lijepljenja Omi razvojnog API ključa.
Interaktivni unos skriva ključ; izbjegavajte njegovo pisanje u naredbi koja će ostati u povijesti terminala.

Za izravan odlazak u preglednik:

```sh
omi auth login --browser
```

Prijavite se na istom računalu na kojem radi terminal: odgovor za provjeru autentičnosti
koristi lokalnu adresu. Slijedite upute na zaslonu.

Nakon toga provjerite konfiguraciju i pristup API-ju:

```sh
omi auth status
omi auth whoami
```

`status` prikazuje lokalno stanje i skriva tajnu, ali ne provjerava valjanost na poslužitelju.
`whoami` šalje autentificirani zahtjev; ako uspije, potvrđuje da vjerodajnice rade, bez nužnog prikazivanja vašeg imena.

Konfiguracija se prema zadanim postavkama sprema u `~/.omi/config.toml`. Nemojte dijeliti
ovu datoteku: može sadržavati vaše povjerljive vjerodajnice.

## Pregled vaših podataka

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prazan popis može jednostavno značiti da nema stavki koje odgovaraju upitu.
Upotrijebite pomoć kako biste otkrili filtre svake naredbe:

```sh
omi memory list --help
omi action-item list --help
```

## Dohvaćanje JSON-a i navigacija po stranicama

Postavite globalnu opciju `--json` **prije** grupe naredbi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prva naredba traži prvih 25 sjećanja; druga, sljedećih 25. Jedna stranica stoga nije
potpuna sigurnosna kopija (backup). JSON izlaz čuva pune identifikatore, dok ih tablice mogu skratiti za prikaz.

Za spremanje stranice u datoteku:

```sh
omi --json memory list --limit 25 --offset 0 > sjecanja-stranica-1.json
```

Ovo preusmjeravanje stvara ili zamjenjuje lokalnu datoteku. Provjerite je li naredba
uspješno završila prije korištenja njezinog sadržaja. Pogreške se zapisuju u izlaz za pogreške (stderr);
prazna datoteka ne jamči da nema podataka. Izvezena datoteka može sadržavati osobne podatke: držite je privatnom.

## Odjava (Logout)

```sh
omi auth logout
```

Ova naredba briše lokalno spremljene vjerodajnice. Da biste opozvali ključ na poslužitelju,
upotrijebite upravljanje razvojnim ključevima na svom računu.

Za ostale naredbe i napredne opcije pogledajte [glavni vodič na engleskom](../README.md) i `omi --help`.
