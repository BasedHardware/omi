# Przewodnik Szybkiego Startu omi-cli (Polski)

> Praktyczny przewodnik interakcji z Omi z poziomu terminala. Odpowiedni zarówno dla osób, jak i agentów AI.

`omi-cli` to oficjalny interfejs wiersza poleceń do interakcji z API deweloperskimi [Omi](https://omi.me). Obsługuje cztery podstawowe zasoby Omi — **pamięci, rozmowy, elementy akcji i cele** — w sposób wydajny i skryptowalny.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Oficjalna dokumentacja:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kod źródłowy:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacja

Zalecaną metodą instalacji jest użycie `pipx` w celu izolacji zależności.

```bash
# Zalecane: instalacja za pomocą pipx
pipx install omi-cli

# Alternatywnie: użyj pip
pip install omi-cli
```

> **Ważne: różnica między nazwą pakietu a nazwą polecenia**
> * Instalowany pakiet Pythona nazywa się **`omi-cli`** (samodzielny pakiet `omi` to inny, niepowiązany pakiet).
> * Nazwa polecenia wykonywalnego w terminalu po instalacji to **`omi`**.

Po instalacji sprawdź wersję i pomoc.

```bash
omi --version
omi --help
```

---

## 2. Uwierzytelnianie

`omi-cli` obsługuje dwa sposoby uwierzytelniania.

| Metoda | Zalecane zastosowanie | Przykładowe polecenie |
| :--- | :--- | :--- |
| **Klucz API dewelopera (`omi_dev_*`)** | CI/CD, automatyczne skrypty, agenci AI | `omi auth login --api-key ...` lub zmienna środowiskowa |
| **OAuth w przeglądarce (Google/Apple)** | Komputer dewelopera / laptop | `omi auth login --browser` |

### Logowanie interaktywne
Bez opcji zostaniesz poproszony o wybór między logowaniem w przeglądarce a wprowadzeniem klucza API.

```bash
omi auth login
# 1) Przeglądarka — zaloguj się kontem Google lub Apple (dla osób)
# 2) Klucz API — wklej klucz deweloperski z app.omi.me (dla agentów/CI)
```

### Bezpośrednie logowanie przez przeglądarkę
```bash
omi auth login --browser
```

### Użycie klucza API
Pobierz klucz deweloperski w **Developer → API Keys** na [app.omi.me](https://app.omi.me), a następnie go skonfiguruj.

```bash
# Ustaw przez polecenie
omi auth login --api-key omi_dev_...

# Lub przez zmienną środowiskową (idealne dla CI/CD lub kontenerów)
export OMI_API_KEY=omi_dev_...
```

### Sprawdzenie statusu uwierzytelnienia
* `omi auth status`: wyświetla lokalny profil, zamaskowany token i datę ważności (działa offline).
* `omi auth whoami`: wysyła rzeczywiste żądanie uwierzytelnienia do serwera Omi (wymaga połączenia sieciowego).

```bash
omi auth status
omi auth whoami
```

Aby się wylogować:
```bash
omi auth logout
```

---

## 3. Podstawowe użycie

Możesz wyświetlać i zarządzać czterema podstawowymi zasobami Omi.

### Pamięci (Memories)
Zarządzaj faktami i wiedzą poznaną przez system.

```bash
# Wyświetl wszystkie pamięci
omi memory list

# Utwórz nową pamięć
omi memory create "Użytkownik preferuje tryb ciemny" --category lifestyle

# Wyświetl szczegóły konkretnej pamięci
omi memory get <MEMORY_ID>
```

### Rozmowy (Conversations)
Historia audio lub tekstu rozmów przechwyconych z urządzenia do noszenia lub aplikacji.

```bash
# Pobierz ostatnie 5 rozmów
omi conversation list --limit 5

# Wyświetl szczegóły rozmowy i transkrypcję
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Elementy akcji (Action Items)
Zadania lub elementy do wykonania wyodrębnione automatycznie z rozmów.

```bash
# Wyświetl tylko otwarte elementy akcji
omi action-item list --open

# Oznacz element akcji jako ukończony
omi action-item complete <ACTION_ITEM_ID>
```

### Cele (Goals)
Zarządzaj celami, których postęp jest śledzony.

```bash
# Wyświetl wszystkie cele
omi goal list
```

---

## 4. Przetwarzanie skryptów i wyjście JSON (`--json`)

`omi-cli` natywnie obsługuje wyjście JSON. W połączeniu z `jq` lub skryptami Pythona, **opcja globalna** `--json` musi być umieszczona przed poleceniem podrzędnym.

```bash
# Pobierz listę pamięci jako JSON i wyodrębnij ID i treść
omi --json memory list | jq '.[] | {id, content, category}'

# Pobierz tytuły ostatnich 5 rozmów
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Wyświetl otwarte elementy akcji
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Wyświetl cele
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Diagnostyka sesji

Użyj tych dwóch poleceń w parze do szybkiego rozwiązywania problemów.

```bash
# 1) Najpierw sprawdź konfigurację lokalną
omi auth status

# 2) Potwierdź z serwerem Omi
omi auth whoami

# 3) Jeśli to konieczne, uruchom ponownie logowanie
omi auth login
```

---

## 6. Najlepsze praktyki

* **Używaj `--json` w skryptach:** Unikaj analizowania wolnego tekstu; zawsze polegaj na ustrukturyzowanym wyjściu JSON.
* **Izoluj środowiska za pomocą `pipx`:** Unika konfliktów zależności z innymi pakietami Pythona.
* **Nie udostępniaj kluczy API:** Klucze `omi_dev_*` zapewniają pełny dostęp do konta — przechowuj je w menedżerze sekretów lub zmiennych środowiskowych.
* **Wyloguj się z urządzeń współdzielonych:** Użyj `omi auth logout` po sesjach na maszynach współdzielonych.

---

## 7. Rozwiązywanie problemów

| Objaw | Prawdopodobna przyczyna | Rozwiązanie |
| :--- | :--- | :--- |
| `command not found: omi` | PATH nie zawiera katalogu bin pipx | Uruchom `pipx ensurepath` i uruchom ponownie terminal |
| `401 Unauthorized` | Klucz API jest nieprawidłowy lub wygasł | Wygeneruj nowy klucz na app.omi.me i zaktualizuj |
| `connection refused` | Brak dostępu sieciowego do serwera Omi | Sprawdź połączenie internetowe i ustawienia proxy |
| `permission denied` na plikach konfiguracyjnych | Katalog konfiguracyjny nie jest zapisywalny | Sprawdź uprawnienia `~/.omi/config.toml` |

---

## 8. Szybkie linki

* Repozytorium źródłowe: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Pełna dokumentacja: [docs.omi.me](https://docs.omi.me)
* Problemy i wsparcie: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Społeczność Discord: zaproszenie dostępne przez stronę główną Omi