# Szybki start z omi-cli

Ten przewodnik opisuje podstawowe polecenia po polsku. Nazwy poleceń i
komunikaty programu pozostają po angielsku. Przykładowe polecenia poniżej nie
zmieniają wspomnień, rozmów, zadań ani celów.

## Instalacja programu

Wymagania: Python 3.10 lub nowszy oraz konto Omi.

Jeśli masz zainstalowany `pipx`:

```sh
pipx install omi-cli
omi --help
```

Alternatywnie zainstaluj w aktywowanym środowisku wirtualnym Pythona:

```sh
python -m pip install omi-cli
omi --help
```

Jeśli terminal nie znajduje `omi`, upewnij się, że środowisko wirtualne jest
aktywne albo że katalog, do którego `pipx` instaluje programy, jest w `PATH`.

## Połączenie konta

Uruchom interaktywny przewodnik:

```sh
omi auth login
```

Wybierz logowanie przez przeglądarkę albo wklej klucz API dewelopera Omi.
Interaktywne wejście ukrywa klucz; nie wpisuj go w polecenia zapisywane w
historii terminala.

Aby od razu użyć przeglądarki:

```sh
omi auth login --browser
```

Zaloguj się na tym samym komputerze co terminal, ponieważ uwierzytelnianie
korzysta z lokalnego adresu zwrotnego. Postępuj zgodnie z instrukcjami na
ekranie.

Po zalogowaniu sprawdź konfigurację i dostęp do API:

```sh
omi auth status
omi auth whoami
```

`status` pokazuje stan lokalny i maskuje tajne wartości, ale nie sprawdza ich
ważności na serwerze. `whoami` wykonuje uwierzytelnione zapytanie; jeśli się
powiedzie, Twoje dane uwierzytelniające działają — bez pokazywania Twojego
imienia.

Konfiguracja jest domyślnie zapisywana w `~/.omi/config.toml`. Nie udostępniaj
tego pliku, ponieważ może zawierać dane uwierzytelniające.

## Odczyt danych

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pusta lista może oznaczać, że żaden element nie pasuje do filtra. Opcje każdego
polecenia zobaczysz w pomocy:

```sh
omi memory list --help
omi action-item list --help
```

## Wynik JSON i stronicowanie

Globalną opcję `--json` podawaj **przed** grupą poleceń:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierwsze polecenie pobiera pierwsze 25 wspomnień, drugie — kolejne 25. Jedna
strona to nie pełna kopia zapasowa. Wynik JSON zachowuje pełne identyfikatory,
a tabela może je skracać na potrzeby wyświetlania.

Aby zapisać stronę do pliku:

```sh
omi --json memory list --limit 25 --offset 0 > memory-strona-1.json
```

Przekierowanie tworzy lub nadpisuje plik lokalny. Zanim użyjesz zawartości,
upewnij się, że polecenie zakończyło się sukcesem. Błędy trafiają na stderr;
pusty plik nie dowodzi braku danych. Wyeksportowany plik może zawierać dane
osobowe — przechowuj go prywatnie.

## Korzystanie z profili

Stan jest zapisywany w `~/.omi/config.toml` (można zmienić przez
`$OMI_CONFIG`). Każdy profil ma własną metodę uwierzytelniania i adres API.
Przełączanie profilu przez `--profile`:

```sh
omi config profile use praca
omi auth login
omi --profile prywatny memory list
```

Typowe polecenia konfiguracji:

```sh
omi config show
omi config path
omi config profile list
```

## Kody wyjścia

Te kody wyjścia są stabilne i przydatne w skryptach oraz dla agentów:

| Kod | Znaczenie | Przykładowa sytuacja |
| ---: | --- | --- |
| 0 | sukces | Polecenie zakończone |
| 1 | błąd użycia | Zła flaga, brak argumentu lub nieudana walidacja |
| 2 | błąd uwierzytelniania | Brak poświadczeń, wygasły token lub brak uprawnień |
| 3 | błąd serwera | Serwer 5xx lub nieudane połączenie |
| 4 | limit żądań | Serwer zwrócił HTTP 429 |
| 5 | nie znaleziono | Serwer zwrócił HTTP 404 |

## Wylogowanie

```sh
omi auth logout
```

Usuwa lokalnie zapisane poświadczenia. Aby unieważnić klucz na serwerze, użyj
zarządzania kluczami deweloperskimi w swoim koncie.

Więcej poleceń i opcji znajdziesz w [angielskim głównym README](../README.md)
oraz po uruchomieniu `omi --help`.
