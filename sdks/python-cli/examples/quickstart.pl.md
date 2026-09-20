# Pierwsze kroki z omi-cli

Ten przewodnik przedstawia podstawowe polecenia w języku polskim. Nazwy poleceń oraz komunikaty programu pozostają w języku angielskim. Przykłady zapytań nie modyfikują ani nie usuwają Twoich wspomnień, rozmów, zadań ani celów.

## Instalacja programu

Wymagania: Python 3.10 lub nowszy oraz konto Omi.

Jeśli masz zainstalowany `pipx`:

```sh
pipx install omi-cli
omi --help
```

Możesz także zainstalować pakiet w aktywnym wirtualnym środowisku Pythona:

```sh
python -m pip install omi-cli
omi --help
```

Jeśli terminal nie odnajduje polecenia `omi`, upewnij się, że wirtualne środowisko jest aktywne lub że katalog instalacyjny `pipx` znajduje się w Twojej zmiennej środowiskowej `PATH`.

## Połączenie konta

Uruchom interaktywny kreator logowania:

```sh
omi auth login
```

Wybierz logowanie przez przeglądarkę lub wklejenie klucza API dewelopera Omi. Interaktywne wprowadzanie ukrywa klucz dla bezpieczeństwa; unikaj wpisywania go bezpośrednio w poleceniach powłoki, aby nie zapisał się w historii.

Aby przejść bezpośrednio do przeglądarki:

```sh
omi auth login --browser
```

Zaloguj się na tym samym komputerze co terminal: odpowiedź uwierzytelniająca korzysta z adresu lokalnego. Postępuj zgodnie z instrukcjami na ekranie.

Następnie zweryfikuj konfigurację i połączenie z API:

```sh
omi auth status
omi auth whoami
```

`status` wyświetla stan pliku lokalnego. `whoami` wykonuje uwierzytelnione zapytanie do serwera, potwierdzając poprawność danych logowania.

Domyślnie konfiguracja jest zapisywana w `~/.omi/config.toml`. Nie udostępniaj tego pliku, ponieważ zawiera Twoje poświadczenia.

## Przeglądanie danych

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pusta lista może po prostu oznaczać brak elementów spełniających kryteria. Użyj pomocy, aby poznać opcje filtrowania dla każdego polecenia:

```sh
omi memory list --help
omi action-item list --help
```

## Format JSON i stronicowanie

Globalną flagę `--json` należy umieścić **przed** grupą poleceń:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierwsze polecenie pobiera pierwsze 25 wspomnień, a drugie kolejne 25. Pojedyncza strona nie stanowi kompletnej kopii zapasowej konta. Dane wyjściowe JSON zachowują pełne identyfikatory UUID.

Aby zapisać stronę do pliku:

```sh
omi --json memory list --limit 25 --offset 0 > wspomnienia-strona-1.json
```

Przed użyciem pliku upewnij się, że polecenie zakończyło się powodzeniem. Wyeksportowany plik może zawierać dane osobowe — przechowuj go bezpiecznie.

## Wylogowanie

```sh
omi auth logout
```

Polecenie to usuwa lokalnie zapisane dane uwierzytelniające. Aby unieważnić klucz na serwerze, skorzystaj z panelu zarządzania kluczami w panelu webowym.

Dodatkowe polecenia i zaawansowane opcje opisano w [głównym podręczniku w języku angielskim](../README.md) oraz w `omi --help`.
