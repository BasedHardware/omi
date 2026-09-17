# Prvi koraki z omi-cli

Ta vodnik razlaga prve ukaze v slovenščini. Imena ukazov in sporočila programa
ostajajo v angleščini. Primeri poizvedb, prikazani tukaj, ne spreminjajo vaših
spominov, pogovorov, opravil ali ciljev.

## Namestitev programa

Zahteve: Python 3.10 ali novejša različica in račun Omi.

Če imate nameščen `pipx`:

```sh
pipx install omi-cli
omi --help
```

Druga možnost je namestitev v aktiviranem navideznem okolju Python
(virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Če terminal ne najde `omi`, preverite, ali je navidezno okolje aktivirano ali pa
je imenik, kamor `pipx` namesti izvedljive datoteke, v vaši spremenljivki `PATH`.

## Povezovanje vašega računa

Zaženite interaktivnega pomočnika:

```sh
omi auth login
```

Izberite prijavo prek brskalnika ali možnost lepljenja razvijalskega API ključa
Omi. Interaktivni vnos skrije ključ; izogibajte se pisanju ključa v ukazu, ki bo
ostal v zgodovini terminala.

Za neposreden prehod v brskalnik:

```sh
omi auth login --browser
```

Prijavite se na istem računalniku, kjer teče terminal: odgovor za preverjanje
pristnosti uporablja lokalni naslov. Sledite navodilom na zaslonu.

Nato preverite konfiguracijo in dostop do API-ja:

```sh
omi auth status
omi auth whoami
```

`status` prikazuje lokalno stanje in skrije skrivnost, vendar ne preveri
veljavnosti na strežniku. `whoami` pošlje overjeno zahtevo; če uspe, potrdi, da
poverilnice delujejo, ne da bi nujno prikazal vaše ime.

Konfiguracija se privzeto shrani v `~/.omi/config.toml`. Te datoteke ne delite
z drugimi: lahko vsebuje vaše zaupne poverilnice.

## Ogled vaših podatkov

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prazen seznam lahko preprosto pomeni, da ni elementov, ki ustrezajo poizvedbi.
Uporabite pomoč, da odkrijete filtre za vsak ukaz:

```sh
omi memory list --help
omi action-item list --help
```

## Pridobivanje JSON-a in krmarjenje po straneh

Postavite globalno možnost `--json` **pred** skupino ukazov:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prvi ukaz zahteva prvih 25 spominov; drugi, naslednjih 25. Ena stran torej ni
popolna varnostna kopija (backup). Izhod JSON ohrani polne identifikatorje,
medtem ko jih tabele na zaslonu lahko skrajšajo za prikaz.

Če želite stran shraniti v datoteko:

```sh
omi --json memory list --limit 25 --offset 0 > spomini-stran-1.json
```

Ta preusmeritev ustvari ali prepiše lokalno datoteko. Pred uporabo vsebine
preverite, ali se je ukaz uspešno zaključil. Napake se izpišejo v izhod za
napake (stderr); prazna datoteka ne zagotavlja, da ni podatkov. Izvožena datoteka
lahko vsebuje osebne podatke: ohranite jo zasebno.

## Odjava iz računa (Logout)

```sh
omi auth logout
```

Ta ukaz izbriše lokalno shranjene poverilnice. Za preklic ključa na strežniku
uporabite upravljanje razvijalskih ključev v svojem računu.

Za ostale ukaze in napredne možnosti glejte
[glavni vodnik v angleščini](../README.md) in `omi --help`.
