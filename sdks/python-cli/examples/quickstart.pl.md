# Przewodnik Szybkiego Startu po omi-cli (Polish Quickstart)

Praktyczny przewodnik po oficjalnym interfejsie wiersza poleceń Omi (`omi-cli`).
Niniejszy dokument opisuje instalację, uwierzytelnianie, podstawowe komendy zarządzania danymi oraz techniki automatyzacji dla skryptów i autonomicznych agentów AI.

---

## Przegląd i Plik Wykonywalny

* **Nazwa pakietu PyPI:** `omi-cli`
* **Polecenie wykonywalne:** `omi`

Aby uniknąć pomyłek podczas instalacji i użytkowania:

```bash
# Instalacja przy użyciu nazwy pakietu:
pipx install omi-cli

# Uruchamianie za pomocą krótkiego polecenia:
omi --help
```

---

## Instalacja

Zaleca się użycie narzędzia `pipx`, aby uruchamiać CLI w odizolowanym środowisku wirtualnym i zapobiec konfliktom zależności.

### Zalecana Metoda (`pipx`)

```bash
pipx install omi-cli
```

Aktualizacja do najnowszej wersji:

```bash
pipx upgrade omi-cli
```

### Metoda Alternatywna (`pip`)

```bash
pip install --user omi-cli
```

Weryfikacja poprawności instalacji:

```bash
omi --version
```

---

## Uwierzytelnianie

CLI obsługuje trzy główne mechanizmy uwierzytelniania: logowanie w przeglądarce, klucz API dewelopera oraz zmienną środowiskową.

### 1. Logowanie w Przeglądarce (OAuth)

Domyślnie używany jest dostawca Google. Aby skorzystać z konta Apple, należy dodać opcję `--provider apple`.

```bash
# Logowanie przez Google (domyślne)
omi auth login --browser

# Logowanie przez konto Apple
omi auth login --browser --provider apple
```

### 2. Logowanie za Pomocą Klucza API (Tryb Bezgłowy / CI/CD)

Odpowiednie dla serwerów zdalnych, sesji SSH i zautomatyzowanych potoków:

```bash
omi auth login --api-key
```

Wklej klucz deweloperski wygenerowany w panelu [app.omi.me](https://app.omi.me) w sekcji **Developer → API Keys**.

### 3. Zmienna Środowiskowa

Dla kontenerów Docker oraz systemów CI/CD bez zapisu na dysku:

```bash
export OMI_API_KEY="omi_dev_twoj_tajny_klucz"
```

> **Wskazówka:** Jeśli profil lokalny posiada już zapisany klucz, użyj najpierw `omi auth logout`, aby zmienna środowiskowa miała pierwszeństwo.

### Sprawdzanie Statusu Uwierzytelnienia

* **Weryfikacja offline:**
  `omi auth status` wyświetla aktywny profil lokalny i zamaskowany klucz. Data wygaśnięcia widoczna jest tylko dla profili OAuth.
* **Weryfikacja online:**
  `omi auth whoami` wysyła żądanie do serwera Omi w celu potwierdzenia ważności poświadczeń w czasie rzeczywistym.

```bash
omi auth status
omi auth whoami
```

Wylogowanie z sesji lokalnej:

```bash
omi auth logout
# Jeśli zmienna OMI_API_KEY jest ustawiona, usuń ją z sesji (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## Podstawowe Przepływy Pracy

### Wspomnienia (`omi memory`)

Wspomnienia reprezentują atomowe jednostki kontekstu zarejestrowane przez Omi.

```bash
# Wyświetlenie ostatnich wspomnień
omi memory list --limit 10

# Ręczne dodanie nowego wspomnienia
omi memory create --text "Spotkanie projektowe we wtorek o 10:00 z zespołem technicznym."

# Wyszukiwanie semantyczne we wspomnieniach
omi memory search "spotkanie projektowe"
```

### Rozmowy (`omi conversation`)

Zarządzanie zarejestrowanymi dialogami i transkrypcjami audio.

```bash
# Wyświetlenie listy rozmów
omi conversation list --limit 5

# Pobranie szczegółów konkretnej rozmowy
omi conversation get conv_123456

# Eksport pełnej transkrypcji w formacie Markdown
omi conversation export conv_123456 --format markdown > transkrypcja.md
```

### Zadania i Akcje (`omi action-item`)

Zadania wyodrębnione automatycznie z rozmów.

```bash
# Lista oczekujących zadań
omi action-item list --status pending

# Oznaczenie zadania jako wykonane
omi action-item update act_789012 --completed
```

### Cele (`omi goal`)

Zarządzanie krótko- i długoterminowymi celami.

```bash
# Wyświetlenie aktywnych celów
omi goal list

# Tworzenie nowego celu
omi goal create --title "Ukończyć dokumentację wielojęzyczną" --horizon month

# Aktualizacja postępu celu
omi goal update goal_345678 --progress 75
```

---

## Strukturyzowana Automatyzacja (`--json` & `jq`)

Każde polecenie akceptuje globalną flagę `--json`, umożliwiając bezpośrednie parsowanie danych wyjściowych przez narzędzia automatyzacji.

### Filtrowanie Danych z `jq`

```bash
# Wyodrębnienie treści wszystkich wspomnień
omi --json memory list --limit 20 | jq -r '.[].content'

# Pobranie identyfikatorów i opisów nieukończonych zadań
omi --json action-item list | jq '.[] | select(.completed == false) | {id: .id, description: .description}'
```

---

## Tabela Kodów Wyjścia (Exit Codes)

| Kod | Znaczenie | Typowa Przyczyna |
| :---: | :--- | :--- |
| `0` | **Sukces (Success)** | Operacja wykonana pomyślnie. |
| `1` | **Błąd Aplikacji / Walidacji** | Błędne wartości danych lub niespełniona walidacja logiki biznesowej; błędy składniowe parsera Click zwracają kod `2`. |
| `2` | **Błąd Uwierzytelniania / Składni CLI** | Brak tokenu, nieważny klucz API bądź niepoprawne opcje/argumenty wiersza poleceń parsera Click. |
| `3` | **Błąd Serwera / Sieci** | Błąd HTTP 5xx, limit czasu połączenia lub serwer nieosiągalny. |
| `4` | **Limit Zapytań (Rate Limit)** | Zwrócony kod HTTP 429 — wymagany mechanizm ponawiania z opóźnieniem. |
| `5` | **Nie Znaleziono (Not Found)** | Zwrócony kod HTTP 404 — wskazany zasób nie istnieje. |

---

## Przykłady Skryptów Wieloplatformowych

### Bash / Zsh (Linux & macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Sprawdzanie uwierzytelnienia Omi..."
if ! omi auth status > /dev/null 2>&1; then
    echo "Błąd: Wymagane logowanie. Uruchom 'omi auth login'." >&2
    exit 2
fi

echo "Tworzenie nowej notatki..."
omi memory create --text "Automatyczna kontrola systemu zakończona sukcesem."
```

### PowerShell (Windows)

```powershell
Write-Host "Sprawdzanie uwierzytelnienia Omi..."
omi auth status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Brak uwierzytelnienia. Uruchom 'omi auth login'."
    exit $LASTEXITCODE
}

Write-Host "Pobieranie celów..."
omi --json goal list | ConvertFrom-Json | ForEach-Object {
    [PSCustomObject]@{
        Id = $_.id
        Tytul = $_.title
        Postep = "$($_.progress)%"
    }
}
```

---

## Integracja z Lokalnym Omi Desktop

W przypadku uruchomionej lokalnie aplikacji Omi Desktop, CLI może odpytywać jej usługi kontekstowe:

```bash
# Konfiguracja portu lokalnego
omi local configure --port 8000

# Wyszukiwanie tekstu na przechwyconym ekranie
omi local search-screen "raport kwartalny"
```

---

## Zarządzanie Wieloma Profilami

Przełączanie konfiguracji pomiędzy środowiskami przy użyciu opcji `--profile` lub pliku `~/.omi/config.toml`:

```bash
# Użycie konkretnego profilu
omi --profile praca memory list

# Profil testowy z osobnym adresem API
omi --profile staging --api-url https://api-staging.omi.me memory list
```

---

## Bezpieczeństwo i Dobre Praktyki

1. **Ochrona Kluczy:** Nigdy nie zatwierdzaj tokenów ani kluczy API do publicznych repozytoriów Git.
2. **Historia Powłoki:** Unikaj przekazywania klucza jako bezpośredniego argumentu w wierszu poleceń na współdzielonych maszynach; preferuj tryb interaktywny lub zmienną `OMI_API_KEY`.
3. **Uprawnienia do Katalogu:** W systemach Unix ogranicz uprawnienia do katalogu konfiguracyjnego `~/.omi/` (`chmod 700 ~/.omi`).
