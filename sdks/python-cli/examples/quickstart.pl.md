# Pierwsze kroki z omi-cli (Polish Quickstart)

Ten przewodnik przedstawia podstawowe polecenia narzędzia `omi-cli` w języku polskim. Nazwy poleceń oraz komunikaty systemowe pozostają w języku angielskim. Przykłady odczytu w tym dokumencie jedynie przeglądają dane — nie modyfikują Twoich wspomnień, rozmów, zadań ani celów.

## 1. Instalacja programu

**Wymagania:** Python 3.10 lub nowszy oraz konto Omi.

> **Ważna uwaga:** W repozytorium PyPI pakiet nosi nazwę **`omi-cli`**, natomiast polecenie uruchamiane w terminalu po instalacji to **`omi`**. W PyPI istnieje inny, niepowiązany pakiet o nazwie `omi` — nie należy go instalować.

Jeśli masz zainstalowane narzędzie `pipx`:

```sh
pipx install omi-cli
omi --help
```

Alternatywnie, w aktywnym środowisku wirtualnym Python (virtualenv):

```sh
python -m pip install omi-cli
omi --help
```

Jeśli terminal nie rozpoznaje polecenia `omi`, upewnij się, że środowisko wirtualne jest aktywne lub katalog wykonywalny `pipx` znajduje się w zmiennej `PATH`.

## 2. Podłączenie konta (Uwierzytelnianie)

Uruchom interaktywnego asystenta logowania:

```sh
omi auth login
```

Wybierz logowanie przez przeglądarkę lub wklejenie klucza deweloperskiego Omi API Key. Logowanie bezpośrednio przez przeglądarkę:

```sh
omi auth login --browser
```

Logowanie należy przeprowadzić na tym samym komputerze, na którym działa terminal, ponieważ autoryzacja przekierowuje na adres lokalny (localhost).

Następnie sprawdź konfigurację i dostęp do API:

```sh
omi auth status
omi auth whoami
```

Polecenie `status` wyświetla stan lokalny i ukrywa poufne dane. `whoami` wysyła żądanie do serwera, potwierdzając poprawne działanie danych uwierzytelniających.

Konfiguracja jest domyślnie zapisywana w pliku `~/.omi/config.toml`. Chroń ten plik, ponieważ zawiera Twoje klucze dostępu.

## 3. Przeglądanie danych

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Aby wyświetlić pełną transkrypcję konkretnej rozmowy:

```sh
omi conversation get <CONVERSATION_ID> --include-transcript
```

Pusta lista oznacza jedynie brak elementów spełniających kryteria zapytania. Aby poznać filtry i opcje dowolnego polecenia, użyj `--help`:

```sh
omi memory list --help
omi conversation list --help
omi goal list --help
```

## 4. Format JSON i paginacja

Globalną flagę `--json` należy zawsze umieszczać **przed** grupą poleceń:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Pierwsze polecenie pobiera pierwsze 25 rekordów; drugie kolejne 25.

Aby zapisać stronę danych do pliku (Export):

```sh
omi --json memory list --limit 25 --offset 0 > wspomnienia-strona-1.json
```

## 5. Wylogowanie

Aby usunąć dane uwierzytelniające z systemu lokalnego:

```sh
omi auth logout
```

To polecenie usuwa dane logowania wyłącznie z komputera lokalnego. Aby całkowicie unieważnić klucz na serwerze, skorzystaj z panelu deweloperskiego Omi.

Więcej szczegółów oraz opcji zaawansowanych znajduje się w głównym przewodniku w języku angielskim: [../README.md](../README.md) oraz [agent_quickstart.md](agent_quickstart.md).
