# Pornire rapidă cu omi-cli

Acest ghid explică în română comenzile de bază. Numele comenzilor și mesajele
programului rămân în engleză. Comenzile de exemplu de mai jos nu modifică
amintirile, conversațiile, acțiunile sau obiectivele tale.

## Instalarea programului

Cerințe: Python 3.10 sau mai nou și un cont Omi.

Dacă `pipx` este instalat:

```sh
pipx install omi-cli
omi --help
```

Alternativ, instalează într-un mediu virtual Python activat:

```sh
python -m pip install omi-cli
omi --help
```

Dacă terminalul nu găsește `omi`, verifică că mediul virtual este activ sau că
directorul în care `pipx` instalează executabilele este în `PATH`.

## Conectarea contului

Rulează ghidul interactiv:

```sh
omi auth login
```

Alege autentificarea prin browser sau lipește o cheie API de developer Omi.
Intrarea interactivă ascunde cheia; nu o scrie în comenzi salvate în istoria
terminalului.

Pentru a folosi direct browserul:

```sh
omi auth login --browser
```

Autentifică-te pe același calculator cu terminalul, deoarece autentificarea
folosește o adresă de callback locală. Urmează instrucțiunile de pe ecran.

După autentificare verifică configurația și accesul API:

```sh
omi auth status
omi auth whoami
```

`status` arată starea locală și maschează secretele, dar nu verifică validitatea
lor pe server. `whoami` trimite o cerere autentificată; dacă reușește,
credențialele tale funcționează fără a-ți afișa numele.

Configurația se salvează implicit în `~/.omi/config.toml`. Nu partaja fișierul
— poate conține credențiale.

## Citirea datelor tale

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

O listă goală poate însemna că niciun element nu se potrivește filtrului. Vezi
opțiunile fiecărei comenzi în ajutor:

```sh
omi memory list --help
omi action-item list --help
```

## Obținerea JSON și parcurgerea paginilor

Pune opțiunea globală `--json` **înaintea** grupului de comenzi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prima comandă cere primele 25 de amintiri, a doua următoarele 25. O pagină nu
este o copie completă de rezervă. Ieșirea JSON păstrează ID-urile complete, în
timp ce tabelul le poate prescurta pentru afișare.

Pentru a salva o pagină într-un fișier:

```sh
omi --json memory list --limit 25 --offset 0 > memory-pagina-1.json
```

Redirectarea creează sau suprascrie un fișier local. Înainte de a folosi
conținutul, asigură-te că comanda s-a terminat cu succes. Erorile merg la
stderr; un fișier gol nu dovedește lipsa datelor. Fișierul exportat poate
conține informații personale — păstrează-l privat.

## Folosirea profilurilor

Starea se salvează în `~/.omi/config.toml` (poate fi schimbată prin
`$OMI_CONFIG`). Fiecare profil are propria metodă de autentificare și propria
adresă API. Schimbi profilul cu `--profile`:

```sh
omi config profile use munca
omi auth login
omi --profile personal memory list
```

Comenzi uzuale de configurare:

```sh
omi config show
omi config path
omi config profile list
```

## Coduri de ieșire

Aceste coduri de ieșire sunt stabile și utile în scripturi sau pentru agenți:

| Cod | Semnificație | Exemplu de situație |
| ---: | --- | --- |
| 0 | succes | Comanda s-a terminat |
| 1 | eroare de utilizare | Flag greșit, argument lipsă sau validare eșuată |
| 2 | eroare de autentificare | Credențiale lipsă, token expirat sau permisiuni insuficiente |
| 3 | eroare de server | Server 5xx sau conexiune eșuată |
| 4 | limitare de rate | Serverul a returnat HTTP 429 |
| 5 | negăsit | Serverul a returnat HTTP 404 |

## Deconectarea

```sh
omi auth logout
```

Elimină credențialele salvate local. Pentru a revoca cheia pe server, folosește
gestionarea cheilor de developer din contul tău.

Pentru mai multe comenzi și opțiuni, consultă [README-ul principal în
engleză](../README.md) și rulează `omi --help`.
