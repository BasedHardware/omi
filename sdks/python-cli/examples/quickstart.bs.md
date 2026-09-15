# Prvi koraci sa omi-cli

Ovaj vodič objašnjava prve komande na bosanskom jeziku. Nazivi komandi i
poruke programa ostaju na engleskom jeziku. Primjeri upita koji su ovdje
prikazani ne mijenjaju vaša sjećanja, razgovore, zadatke niti ciljeve.

## Instalacija programa

Zahtjevi: Python 3.10 ili novija verzija i Omi nalog.

Ako imate instaliran `pipx`:

```sh
pipx install omi-cli
omi --help
```

Kao alternativa, možete ga instalirati unutar aktiviranog Python virtuelnog
okruženja (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ako terminal ne pronalazi `omi`, provjerite je li virtuelno okruženje aktivirano
ili se direktorij u koji `pipx` instalira izvršne datoteke nalazi u vašem `PATH`-u.

## Povezivanje vašeg naloga

Pokrenite interaktivnog asistenta:

```sh
omi auth login
```

Odaberite prijavu putem pretraživača ili opciju lijepljenja Omi programerskog
API ključa. Interaktivni unos skriva ključ; izbjegavajte njegovo pisanje u
komandi koja će ostati u historiji terminala.

Za direktan odlazak u pretraživač:

```sh
omi auth login --browser
```

Prijavite se na istom računaru na kojem je pokrenut terminal: odgovor za
autentifikaciju koristi lokalnu adresu. Pratite uputstva na ekranu.

Nakon toga provjerite konfiguraciju i pristup API-ju:

```sh
omi auth status
omi auth whoami
```

`status` prikazuje lokalno stanje i skriva tajnu, ali ne provjerava valjanost
na serveru. `whoami` šalje autentificirani zahtjev; ako uspije, potvrđuje da
vjerodajnice rade, bez nužnog prikazivanja vašeg imena.

Konfiguracija se automatski sprema u `~/.omi/config.toml`. Nemojte dijeliti
ovu datoteku: može sadržavati vaše povjerljive pristupne podatke.

## Pregled vaših podataka

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prazna lista može jednostavno značiti da nema stavki koje odgovaraju upitu.
Koristite pomoć da otkrijete filtere za svaku komandu:

```sh
omi memory list --help
omi action-item list --help
```

## Dobijanje JSON formata i navigacija kroz stranice

Postavite globalnu opciju `--json` **prije** grupe komandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prva komanda traži prvih 25 sjećanja; druga, sljedećih 25. Jedna stranica stoga
nije potpuna sigurnosna kopija (backup). JSON izlaz čuva pune identifikatore,
dok ih tabele na ekranu mogu skratiti radi prikaza.

Za spremanje stranice u datoteku:

```sh
omi --json memory list --limit 25 --offset 0 > sjecanja-stranica-1.json
```

Ovo preusmjeravanje kreira ili zamjenjuje lokalnu datoteku. Provjerite je li
komanda uspješno završila prije korištenja njenog sadržaja. Greške se ispisuju
na izlaz za greške (stderr); prazna datoteka ne garantuje da nema podataka.
Izvezena datoteka može sadržavati lične podatke: čuvajte je privatnom.

## Odjava sa naloga (Logout)

```sh
omi auth logout
```

Ova komanda briše lokalno spremljene vjerodajnice. Da biste opozvali ključ na
serveru, koristite upravljanje programerskim ključevima na vašem nalogu.

Za ostale komande i napredne opcije, pogledajte
[glavni vodič na engleskom](../README.md) i `omi --help`.
