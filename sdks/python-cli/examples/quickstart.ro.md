# Primii pași cu omi-cli

Acest ghid explică primele comenzi în limba română. Numele comenzilor și
mesajele programului rămân în engleză. Exemplele de comenzi din ghid nu îți
modifică amintirile, conversațiile, sarcinile sau obiectivele.

> `README.md` în engleză rămâne sursa de referință pentru tot ce este descris
> pe scurt aici.

## Instalare

Sunt necesare Python 3.10 sau o versiune mai nouă și un cont Omi.

Dacă ai `pipx` instalat:

```sh
pipx install omi-cli
omi --help
```

Alternativ, instalează într-un mediu virtual activat:

```sh
python -m pip install omi-cli
omi --help
```

Notă: pachetul Python se numește `omi-cli`, iar comanda rulată în terminal
este `omi`. Dacă terminalul nu găsește `omi`, verifică dacă mediul virtual
este activat sau dacă directorul în care `pipx` instalează executabilele se
află în `PATH`.

## Autentificare

Pornește autentificarea interactivă:

```sh
omi auth login
```

Alege autentificarea prin browser sau introducerea unei chei API de
dezvoltator. Introducerea interactivă ascunde cheia — evită să o scrii direct
în comandă, pentru că acea comandă rămâne în istoricul terminalului.

Autentificare prin browser:

```sh
omi auth login --browser
```

Autentifică-te pe același computer pe care rulează terminalul — răspunsul de
autentificare folosește o adresă locală. Urmează instrucțiunile afișate pe
ecran.

După ce autentificarea se încheie, verifică configurația și accesul la API:

```sh
omi auth status
omi auth whoami
```

`status` afișează starea locală și maschează partea secretă, dar nu verifică
dacă acreditările sunt valide pe server. `whoami` trimite o cerere
autentificată; dacă reușește, confirmă că acreditările funcționează, chiar
dacă nu îți afișează neapărat numele.

Configurația este salvată implicit în `~/.omi/config.toml`. Nu partaja acest
fișier — poate conține acreditările tale.

Pentru automatizare poți folosi variabila de mediu `OMI_API_KEY` atunci când
profilul activ nu are o cheie salvată; în caz contrar se folosește cheia din
profil:

```sh
export OMI_API_KEY=omi_dev_...
omi memory list
```

Pentru deconectare rulează `omi auth logout` — șterge acreditările salvate
local. Pentru revocarea cheii pe server folosește pagina de chei de
dezvoltator din contul tău.

## Explorarea datelor

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

O listă goală poate însemna pur și simplu că nu există elemente care
corespund interogării. Poți descoperi filtrele fiecărei comenzi prin ajutor:

```sh
omi memory list --help
omi action-item list --help
```

## Ieșirea JSON și paginarea

Opțiunea globală `--json` se plasează **înaintea** grupului de comenzi:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prima comandă cere primele 25 de amintiri; a doua, următoarele 25. O singură
pagină nu este, așadar, o copie completă a datelor. Ieșirea JSON păstrează
identificatorii compleți, în timp ce tabelele îi pot scurta pentru
lizibilitate.

Salvarea unei pagini într-un fișier:

```sh
omi --json memory list --limit 25 --offset 0 > amintiri-pagina-1.json
```

Această redirecționare creează sau înlocuiește un fișier local. Verifică dacă
comanda s-a încheiat cu succes înainte de a folosi conținutul. Erorile sunt
afișate pe ieșirea standard de erori; un fișier gol nu garantează că nu
există date. Fișierul exportat poate conține date personale — păstrează-l
privat.

## Profiluri

Pentru mai multe conturi sau medii folosește opțiunea `--profile` (sau `-p`):

```sh
omi --profile serviciu auth login
omi --profile serviciu memory list
```

Dacă nu o specifici, se folosește profilul din variabila `OMI_PROFILE`, apoi
profilul activ din configurație (implicit `default`). Toate profilurile sunt
salvate în `~/.omi/config.toml`.

## Coduri de ieșire

Pentru scripturi și automatizări sunt definite coduri de ieșire stabile:

| Cod | Semnificație | Detalii |
| :---: | :--- | :--- |
| `0` | Succes | Comanda s-a încheiat cu succes |
| `1` | Eroare de utilizare | Utilizare incorectă raportată de CLI (de exemplu, opțiuni care se exclud reciproc) |
| `2` | Eroare de autentificare sau argumente | Lipsesc acreditările, token expirat sau permisiuni insuficiente; și erori de argumente (opțiune necunoscută, argument lipsă, valoare în afara intervalului) |
| `3` | Eroare de server | Răspuns 5xx, conexiune întreruptă, probleme de rețea |
| `4` | Limită de rată | 429 Too Many Requests |
| `5` | Negăsit | 404 Not Found (ID-ul cerut nu există) |

Codul `4` este adesea tranzitoriu — așteaptă puțin și încearcă din nou; CLI-ul
repetă automat cererile limitate (429) și respectă `Retry-After` când
serverul îl trimite. Codul `3` este de obicei tranzitoriu pentru operațiile de
citire, dar la scriere poate însemna că rezultatul este necunoscut (`outcome
unknown`) — este posibil ca serverul să fi aplicat deja modificarea; verifică
resursa înainte de a reîncerca. Codul `2` înseamnă de obicei că trebuie să te
autentifici din nou (`omi auth login`), iar codul `5` că ID-ul cerut nu
există sau nu este disponibil.

Pentru restul comenzilor și opțiunile avansate, vezi
[README-ul principal în engleză](../README.md) și `omi --help`.
