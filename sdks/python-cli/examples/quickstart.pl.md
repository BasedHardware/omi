# Pierwsze kroki z omi-cli

Ten przewodnik wyjaśnia podstawowe polecenia w języku polskim. Nazwy poleceń oraz
komunikaty programu pozostają w języku angielskim. Przykłady zapytań nie modyfikują
Twoich wspomnień, rozmów, zadań ani celów.

## Instalacja programu

Wymagania: Python 3.10 lub nowszy oraz konto Omi.

Jeśli masz zainstalowane `pipx`:

```sh
pipx install omi-cli
omi --help
```

Można również zainstalować narzędzie w aktywnym środowisku wirtualnym (virtual environment)
Pythona:

```sh
python -m pip install omi-cli
omi --help
```

Jeśli terminal nie odnajduje polecenia `omi`, upewnij się, że środowisko wirtualne
jest aktywne lub katalog instalacyjny `pipx` znajduje się w Twojej zmiennej `PATH`.

## Połącz swoje konto

Uruchom interaktywnego asystenta logowania:

```sh
omi auth login
```

Wybierz logowanie przez przeglądarkę lub wklej klucz API dewelopera Omi.
Wprowadzanie interaktywne ukrywa wpisywany klucz; unikaj przekazywania go w jawnym
poleceniu, które mogłoby zostać zapisane w historii terminala.

Aby przejść bezpośrednio do logowania w przeglądarce:

```sh
omi auth login --browser
```

Zaloguj się na tym samym komputerze, na którym uruchomiony jest terminal: odpowiedź
autoryzacyjna korzysta z adresu lokalnego. Postępuj zgodnie z instrukcjami na ekranie.

Następnie zweryfikuj konfigurację i dostęp do API:

```sh
omi auth status
omi auth whoami
```

Polecenie `status` wyświetla stan lokalnej konfiguracji i maskuje klucz, lecz nie
sprawdza jego ważności na serwerze. Polecenie `whoami` wysyła uwierzytelnione zapytanie;
jeśli zakończy się sukcesem, potwierdza poprawność poświadczeń bez konieczności
ujawniania Twojego imienia.

Konfiguracja jest domyślnie zapisywana w pliku `~/.omi/config.toml`. Nie udostępniaj
tego pliku: może on zawierać Twoje poufne dane uwierzytelniające.

## Przeglądaj swoje dane

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pusta lista może po prostu oznaczać brak elementów spełniających kryteria zapytania.
Użyj pomocy, aby poznać opcje filtrowania dla każdego polecenia:

```sh
omi memory list --help
omi action-item list --help
```

## Pobieranie danych w formacie JSON i stronicowanie

Umieść opcję globalną `--json` **przed** grupą poleceń:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierwsze polecenie pobiera pierwsze 25 wspomnień, a drugie kolejną partię 25.
Pojedyncza strona nie stanowi kompletnej kopii zapasowej (backup). Format JSON zachowuje
pełne identyfikatory, podczas gdy widok tabelaryczny może je skracać na ekranie.

Aby zapisać stronę do pliku:

```sh
omi --json memory list --limit 25 --offset 0 > wspomnienia-strona-1.json
```

Przekierowanie strumienia tworzy lub nadpisuje plik lokalny. Upewnij się, że polecenie
zakończyło się sukcesem przed użyciem pliku. Ewentualne błędy trafiają do strumienia
błędów (stderr); pusty plik nie gwarantuje braku danych. Wyeksportowany plik może
zawierać dane osobowe: chroń jego prywatność.

## Wylogowanie (Logout)

```sh
omi auth logout
```

Polecenie to usuwa lokalnie zapisane poświadczenia. Aby unieważnić klucz na serwerze,
skorzystaj z panelu zarządzania kluczami deweloperskimi na swoim koncie.

Więcej poleceń oraz zaawansowane opcje znajdziesz w
[głównym przewodniku w języku angielskim](../README.md) oraz pod poleceniem `omi --help`.
