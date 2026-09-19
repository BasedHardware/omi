# Pierwsze kroki z omi-cli

Ten przewodnik opisuje pierwsze polecenia narzędzia omi-cli po polsku. Nazwy
poleceń i komunikaty programu pozostają w języku angielskim. Wszystkie
przykłady są wyłącznie do odczytu lub działają lokalnie — nie zmieniają Twoich
wspomnień (memories), rozmów (conversations), zadań (action items) ani celów
(goals).

## Instalacja programu

Wymagania: Python 3.10 lub nowszy oraz konto Omi.

Jeśli masz zainstalowany program `pipx`:

```sh
pipx install omi-cli
omi --help
```

Narzędzie możesz też zainstalować w aktywnym środowisku wirtualnym Pythona:

```sh
python -m pip install omi-cli
omi --help
```

Jeśli terminal nie znajduje polecenia `omi`, upewnij się, że środowisko
wirtualne jest aktywne albo że katalog, do którego `pipx` instaluje programy,
znajduje się w zmiennej `$PATH`.

## Połączenie z Twoim kontem

Uruchom interaktywnego asystenta:

```sh
omi auth login
```

Wybierz logowanie przez przeglądarkę albo wklejenie klucza API dewelopera Omi.
Interaktywne wprowadzanie klucza jest ukrywane — unikaj podawania go
bezpośrednio w poleceniu, które trafi do historii terminala.

Aby od razu otworzyć przeglądarkę:

```sh
omi auth login --browser
```

Zaloguj się na tym samym komputerze, na którym działa terminal: odpowiedź
uwierzytelniająca trafia na lokalny adres. Postępuj zgodnie z instrukcjami na
ekranie.

Następnie sprawdź konfigurację i dostęp do API:

```sh
omi auth status
omi auth whoami
```

Polecenie `status` pokazuje stan lokalny i ukrywa dane tajne, ale nie weryfikuje
ich ważności na serwerze. Polecenie `whoami` wykonuje uwierzytelnione żądanie:
jeśli się powiedzie, potwierdza to, że poświadczenia działają, choć nie musi
przy tym pokazywać Twojej nazwy.

Konfiguracja jest domyślnie zapisywana w pliku `~/.omi/config.toml`. Nie
udostępniaj tego pliku — może zawierać poufne poświadczenia.

## Przeglądanie Twoich danych

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pusta lista może po prostu oznaczać, że żaden element nie pasuje do zapytania.
Skorzystaj z pomocy, aby poznać filtry dostępne dla każdego polecenia:

```sh
omi memory list --help
omi action-item list --help
```

## Pobieranie danych w formacie JSON i stronicowanie

Globalną opcję `--json` podaje się **przed** grupą polecenia:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierwsze polecenie pobiera pierwszych 25 wspomnień, drugie — kolejnych 25.
Pojedyncza strona nie jest pełną kopią zapasową. Wynik JSON zachowuje pełne
identyfikatory, podczas gdy tabele na ekranie mogą je skracać.

Aby zapisać jedną stronę do pliku:

```sh
omi --json memory list --limit 25 --offset 0 > wspomnienia-strona-1.json
```

To przekierowanie tworzy nowy plik lub nadpisuje istniejący. Upewnij się, że
polecenie zakończyło się powodzeniem, zanim użyjesz zawartości pliku. Błędy
trafiają na standardowe wyjście błędów (stderr), więc pusty plik nie jest
dowodem na brak danych. Wyeksportowany plik może zawierać dane osobowe —
przechowuj go prywatnie.

## Wylogowanie z konta

```sh
omi auth logout
```

To polecenie usuwa poświadczenia zapisane lokalnie. Aby unieważnić klucz po
stronie serwera, skorzystaj z zarządzania kluczem dewelopera na swoim koncie.

Więcej poleceń i opcji znajdziesz w [głównym README w języku angielskim](../README.md) oraz w `omi --help`.
