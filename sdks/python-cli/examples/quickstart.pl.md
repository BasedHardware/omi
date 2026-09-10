# Przewodnik szybkiego startu omi-cli (Polish Quickstart)

> Praktyczny przewodnik po obsłudze Omi bezpośrednio z terminala — stworzony dla programistów i autonomicznych agentów AI.

`omi-cli` to oficjalny interfejs wiersza poleceń dla API deweloperskiego [Omi](https://omi.me). Zapewnia ustrukturyzowany, programowalny dostęp do 4 kluczowych zasobów ekosystemu: wspomnień (memories), rozmów (conversations), zadań (action items) oraz celów (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Oficjalna dokumentacja:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kod źródłowy:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacja

Zaleca się instalację za pośrednictwem narzędzia `pipx`, co pozwala na uruchamianie CLI w izolowanym środowisku wirtualnym i zapobiega konfliktom zależności systemowych.

```bash
# Zalecane: instalacja w izolowanym środowisku za pomocą pipx
pipx install omi-cli

# Lub standardowa instalacja przez pip
pip install omi-cli
```

> **Ważna uwaga: nazwa pakietu a nazwa polecenia**
> * Nazwa pakietu w rejestrze PyPI to **`omi-cli`** (pakiet `omi` jest niepowiązaną biblioteką).
> * Polecenie wykonywalne w powłoce to po prostu **`omi`**.

Weryfikacja instalacji:

```bash
omi --version
omi --help
```

---

## 2. Uwierzytelnianie (Authentication)

`omi-cli` obsługuje dwa główne mechanizmy uwierzytelniania:

| Metoda | Zastosowanie | Polecenie |
| :--- | :--- | :--- |
| **Klucz API dewelopera (`omi_dev_*`)** | Automatyzacja, CI/CD, serwery bezgłowe, agenci AI | `omi auth login --api-key` lub zmienna `OMI_API_KEY` |
| **OAuth w przeglądarce (Google/Apple)** | Lokalne stacje robocze programistów | `omi auth login --browser` (Google) / `--provider apple` |

### Logowanie interaktywne
Uruchomienie polecenia bez opcji wyświetla menu wyboru:

```bash
omi auth login
# 1) Browser — logowanie przez przeglądarkę (domyślnie Google; dla Apple użyj `--provider apple`)
# 2) API key — interaktywne wprowadzenie klucza z app.omi.me
```

### Bezpośrednie logowanie przez przeglądarkę
```bash
# Logowanie przez konto Google (domyślne)
omi auth login --browser

# Logowanie przez konto Apple
omi auth login --browser --provider apple
```

### Uwierzytelnianie kluczem API
Wygeneruj klucz w panelu [app.omi.me](https://app.omi.me) w sekcji **Developer → API Keys**:

```bash
# Zapisanie w lokalnym profilu za pomocą polecenia
omi auth login --api-key omi_dev_...

# Lub ustawienie zmiennej środowiskowej (idealne dla kontenerów i potoków CI/CD)
# Uwaga: jeśli w aktywnym profilu zapisano już klucz, najpierw wykonaj `omi auth logout`.
export OMI_API_KEY="omi_dev_twoj_klucz_tutaj"
```

### Weryfikacja sesji
* `omi auth status`: wyświetla aktywny profil i zamaskowane dane uwierzytelniające. Daty wygaśnięcia widoczne są tylko dla profili OAuth (działa offline).
* `omi auth whoami`: wysyła zapytanie do serwerów Omi, potwierdzając ważność tokena (wymaga połączenia sieciowego).

```bash
omi auth status
omi auth whoami
```

Zakończenie sesji:
```bash
omi auth logout
# Jeśli zdefiniowano OMI_API_KEY w środowisku, wyczyść zmienną (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Główne polecenia

### Wspomnienia (Memories)
Dyskretne, zsyntetyzowane informacje kontekstowe zapisane przez Omi:

```bash
# Pobranie listy wspomnień
omi memory list

# Utworzenie nowego wspomnienia (tekst jako argument pozycyjny)
omi memory create "Preferuje zwięzłe odpowiedzi techniczne z przykładami w Pythonie" --category work

# Szczegóły konkretnego wspomnienia
omi memory get <ID_WSPOMNIENIA>
```

### Rozmowy (Conversations)
Historia audio i transkrypcje zarejestrowane przez urządzenia Omi:

```bash
# Lista 5 ostatnich rozmów
omi conversation list --limit 5

# Szczegóły rozmowy wraz z pełną transkrypcją
omi conversation get <ID_ROZMOWY> --include-transcript

# Eksport pełnej transkrypcji do pliku JSON
omi --json conversation get <ID_ROZMOWY> --include-transcript > transkrypcja.json
```

### Zadania (Action Items)
Elementy do wykonania wyodrębnione automatycznie z rozmów:

```bash
# Lista otwartych zadań
omi action-item list --open

# Oznaczenie zadania jako ukończone
omi action-item complete <ID_ZADANIA>
```

### Cele (Goals)
Śledzenie postępów i wskaźników długoterminowych:

```bash
# Lista aktywnych celów
omi goal list

# Utworzenie nowego celu ilościowego (tytuł jako argument pozycyjny)
omi goal create "Picie 2 litrów wody dziennie" --type numeric --target 2 --unit liters
```

---

## 4. Automatyzacja i format JSON (`--json`)

Interfejs `omi-cli` został zoptymalizowany pod kątem automatyzacji i integracji z narzędziami takimi jak `jq`. Przekazanie flagi globalnej `--json` gwarantuje czysty format wyjściowy:

```bash
# Pobranie wspomnień w formacie JSON i ekstrakcja pól za pomocą jq
omi --json memory list | jq '.[] | {id, content, category}'

# Odczyt tytułów ostatnich rozmów
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Przegląd surowych danych otwartych zadań
omi --json action-item list --open | jq '.'
```

> **Ważna zasada składni:**
> Flaga `--json` jest **opcją globalną** i musi występować **przed** podpoleceniem:
> * Prawidłowo: `omi --json memory list`
> * Nieprawidłowo: `omi memory list --json`

---

## 5. Kody wyjścia (Exit Codes)

Standardowe kody zakończenia umożliwiające precyzyjną obsługę błędów w skryptach powłoki:

| Kod wyjścia | Znaczenie | Opis |
| :---: | :--- | :--- |
| `0` | **Sukces (Success)** | Polecenie wykonane pomyślnie. |
| `1` | **Błąd walidacji danych** | Nieprawidłowe wartości argumentów lub błędy reguł biznesowych; błędy składni parsera Click zwracają kod `2`. |
| `2` | **Błąd uwierzytelniania / błąd składni Click** | Brak aktywnej sesji, wygasły token lub niepoprawna składnia polecenia Click. |
| `3` | **Błąd serwera / sieci** | Odpowiedź HTTP 5xx, przekroczenie limitu czasu połączenia lub serwer nieosiągalny. |
| `4` | **Limit zapytań (Rate Limit)** | HTTP 429 Too Many Requests — wymagane odczekanie przed ponowieniem. |
| `5` | **Nie znaleziono (Not Found)** | HTTP 404 Not Found — żądany zasób nie istnieje. |

---

## 6. Przykłady skryptów powłoki

### Bash / Zsh (Linux / macOS)
```bash
#!/usr/bin/env bash
set -euo pipefail

# Weryfikacja sesji za pomocą whoami (zwraca kod != 0 przy braku autoryzacji)
if ! omi auth whoami > /dev/null 2>&1; then
    echo "Błąd: Wymagane logowanie. Uruchom 'omi auth login'." >&2
    exit 2
fi

# Pobranie otwartych zadań i przetworzenie JSON
open_items=$(omi --json action-item list --open)
echo "Znalezione zadania: $(echo "$open_items" | jq 'length')"
```

### PowerShell (Windows)
```powershell
# Ustawienie zmiennej sesji
$env:OMI_API_KEY = "omi_dev_twoj_klucz_tutaj"

# Pobranie danych i konwersja JSON do obiektu PowerShell
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Sprawdzenie kodu wyjścia
if ($LASTEXITCODE -ne 0) {
    Write-Error "Polecenie Omi zakończyło się kodem błędu $LASTEXITCODE."
}
```

---

## 7. Integracja z lokalnym Desktop API

Gdy aplikacja Omi Desktop działa lokalnie na komputerze, CLI umożliwia bezpośrednią komunikację bez odpytywania chmury:

```bash
# Konfiguracja punktu końcowego i tokenu
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Sprawdzenie statusu połączenia lokalnego
omi --json local status

# Wyszukiwanie zarejestrowanego tekstu na ekranie
omi --json local search-screen "raport kwartalny" --days 7 --app Safari
```

---

## 8. Zarządzanie wieloma profilami (Profiles)

Opcja `--profile` umożliwia separację kont prywatnych, służbowych i środowisk testowych. Konfiguracja przechowywana jest w pliku `~/.omi/config.toml`:

```bash
# Logowanie do profilu osobistego
omi --profile personal auth login

# Logowanie do profilu służbowego
omi --profile work auth login

# Wywołanie polecenia w kontekście wybranego profilu
omi --profile work memory list
```

---

## 9. Najlepsze praktyki bezpieczeństwa

* **Nigdy nie dodawaj kluczy do repozytorium Git:** Zawsze korzystaj z menedżerów haseł, zmiennych środowiskowych lub plików `.env` ignorowanych w `.gitignore`.
* **Ochrona historii powłoki:** Unikaj przekazywania klucza bezpośrednio w argumentach poleceń w systemach współdzielonych.
* **Uprawnienia katalogu:** W systemach Unix zabezpiecz katalog konfiguracyjny restrykcyjnymi uprawnieniami (`chmod 700 ~/.omi`).
