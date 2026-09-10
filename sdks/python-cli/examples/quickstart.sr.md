# Prvi koraci sa omi-cli

Ovaj vodič objašnjava prve komande na srpskom jeziku. Nazivi komandi i poruke
programa ostaju na engleskom. Primeri komandi u vodiču ne menjaju tvoje
memorije, razgovore, zadatke ni ciljeve.

> Engleski `README.md` ostaje izvor istine za sve što je ovde ukratko opisano.

## Instalacija

Potrebni su Python 3.10 ili noviji i nalog na Omi.

Ako imaš instaliran `pipx`:

```sh
pipx install omi-cli
omi --help
```

Alternativa je instalacija unutar aktiviranog virtuelnog okruženja:

```sh
python -m pip install omi-cli
omi --help
```

Napomena: Python paket se zove `omi-cli`, a komanda koja se pokreće u
terminalu je `omi`. Ako terminal ne pronađe `omi`, proveri da je virtuelno
okruženje aktivirano ili da je direktorijum u koji `pipx` smešta izvršne
fajlove na `PATH`-u.

## Prijavljivanje

Pokreni interaktivnu prijavu:

```sh
omi auth login
```

Izaberi prijavu preko pregledača ili unos razvojnog API ključa. Interaktivni
unos sakriva ključ — izbegavaj da ga upisuješ direktno u komandu, jer takva
komanda ostaje zapisana u istoriji terminala.

Prijava preko pregledača:

```sh
omi auth login --browser
```

Prijavi se na istom računaru na kom radi terminal — odgovor za prijavu koristi
lokalnu adresu. Prati uputstva koja se prikazuju na ekranu.

Kada je prijava završena, proveri konfiguraciju i pristup API-ju:

```sh
omi auth status
omi auth whoami
```

`status` prikazuje lokalno stanje i maskira tajni deo, ali ne proverava da li
su akreditive važeće na serveru. `whoami` šalje autentifikovani zahtev; ako
uspe, potvrđuje da akreditive rade, iako ne mora da prikaže tvoje ime.

Konfiguracija se podrazumevano čuva u `~/.omi/config.toml`. Ne deli ovaj
fajl — može da sadrži tvoje akreditive.

Za automatizaciju možeš koristiti promenljivu okruženja `OMI_API_KEY` umesto
čuvanja profila:

```sh
export OMI_API_KEY=omi_dev_...
omi memory list
```

Za odjavu pokreni `omi auth logout` — time se brišu lokalno sačuvane
akreditive. Za opoziv ključa na serveru koristi stranicu sa razvojnim
ključevima svog naloga.

## Pregled podataka

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prazna lista može jednostavno da znači da nema stavki koje odgovaraju upitu.
Filtere svake komande možeš otkriti preko pomoći:

```sh
omi memory list --help
omi action-item list --help
```

## JSON izlaz i straničenje

Globalnu opciju `--json` postavi **pre** grupe komandi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prva komanda traži prvih 25 memorija; druga sledećih 25. Jedna stranica zato
nije potpuna kopija podataka. JSON izlaz zadržava pune identifikatore, dok ih
tabele mogu skratiti radi preglednosti.

Čuvanje jedne stranice u fajl:

```sh
omi --json memory list --limit 25 --offset 0 > memorije-stranica-1.json
```

Ovakvo preusmeravanje kreira ili zamenjuje lokalni fajl. Proveri da je
komanda uspešno završena pre nego što koristiš sadržaj. Greške se ispisuju na
standardni izlaz za greške; prazan fajl ne garantuje da podataka nema.
Izvezeni fajl može da sadrži lične podatke — čuvaj ga privatno.

## Profili

Za više naloga ili okruženja koristi opciju `--profile` (ili `-p`):

```sh
omi --profile posao auth login
omi --profile posao memory list
```

Ako je ne navedeš, koristi se profil iz promenljive `OMI_PROFILE`, a zatim
podrazumevani profil `default`. Svi profili se čuvaju u `~/.omi/config.toml`.

## Izlazni kodovi

Za skripte i automatizaciju definisani su stabilni izlazni kodovi:

| Kod | Značenje | Detalji |
| :---: | :--- | :--- |
| `0` | Uspeh | Komanda je uspešno završena |
| `1` | Greška u korišćenju | Neispravne opcije, nedostajući argumenti, validacija |
| `2` | Greška prijave | Nema akreditiva, istekao token ili nedovoljna dozvola |
| `3` | Greška servera | 5xx odgovor, prekid veze, mrežni problemi |
| `4` | Ograničenje brzine | 429 Too Many Requests |
| `5` | Nije pronađeno | 404 Not Found (traženi ID ne postoji) |

Kodovi `3` i `4` su često prolazni — sačekaj kratko pa pokušaj komandu ponovo.
CLI automatski ponavlja zahteve koji su ograničeni brzinom (429) i poštuje
`Retry-After` kada ga server pošalje. Kod `2` obično znači da treba ponovo da
se prijaviš (`omi auth login`), a kod `5` da traženi ID ne postoji ili nije
dostupan.

Za ostale komande i napredne opcije pogledaj
[glavni README na engleskom](../README.md) i `omi --help`.
