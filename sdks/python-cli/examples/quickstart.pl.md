# omi-cli — polski przewodnik szybkiego startu

> Praktyczny przewodnik do pracy z Omi z poziomu terminala. Odpowiedni zarówno dla ludzi, jak i dla agentów AI.

`omi-cli` to oficjalny klient wiersza poleceń dla API deweloperskiego [Omi](https://omi.me).
Zapewnia szybki i skryptowalny dostęp do czterech głównych encji Omi:
wspomnienia, rozmowy, elementy działań i cele.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Dokumentacja:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Kod źródłowy:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Instalacja

Zalecaną metodą jest `pipx`: instaluje narzędzie w izolowanym środowisku,
dzięki czemu jego zależności nie kolidują z Twoimi projektami.

```bash
# zalecane: instalacja przez pipx
pipx install omi-cli

# lub przez pip
pip install omi-cli
```

> **Ważne: nazwa pakietu i nazwa polecenia są różne.**
> * Instalowany pakiet to **`omi-cli`** (osobny pakiet `omi` to inny, niepowiązany projekt).
> * Po instalacji uruchamia się polecenie **`omi`**.

Sprawdź, czy wszystko działa:

```bash
omi --version
omi --help
```

---

## 2. Uwierzytelnianie

`omi-cli` obsługuje dwie metody logowania.

| Metoda | Odpowiednia dla | Polecenie |
| :--- | :--- | :--- |
| **Klucz deweloperski (`omi_dev_*`)** | CI/CD, skrypty, agenci AI | `omi auth login --api-key ...` lub zmienna środowiskowa |
| **Logowanie przez przeglądarkę (Google/Apple)** | Praca na własnym komputerze | `omi auth login --browser` |

### Logowanie interaktywne

Uruchom bez opcji — zapyta, której metody chcesz użyć.

```bash
omi auth login
# 1) Browser — zaloguj przez Google lub Apple (dla ludzi)
# 2) API key — wklej klucz deweloperski z app.omi.me (dla agentów/CI)
```

Jeśli wybierzesz klucz, wprowadzenie zostanie ukryte, więc klucz nie trafi do historii terminala.

### Logowanie bezpośrednio przez przeglądarkę

```bash
omi auth login --browser
```

### Logowanie kluczem deweloperskim

Klucz uzyskasz na [app.omi.me](https://app.omi.me) w sekcji **Developer → API Keys**.

```bash
# zapisz klucz w konfiguracji
omi auth login --api-key omi_dev_...

# lub przekaż przez środowisko — lepiej dla CI/CD i kontenerów
export OMI_API_KEY=omi_dev_...
```

Zmienna środowiskowa `OMI_API_KEY` jest używana, gdy w aktywnym profilu nie ma
zapisanego klucza, więc w kontenerze nic nie trzeba zapisywać na dysku. Jeśli profil
ma już klucz, ma on pierwszeństwo przed zmienną środowiskową.

### Zweryfikuj dostęp

Dwa polecenia odpowiadają na różne pytania — nie myl ich:

* `omi auth status` — co jest zapisane **lokalnie**: profil, zamaskowany klucz, data wygaśnięcia.
  Działa bez sieci.
* `omi auth whoami` — żądanie **do serwera Omi**: sprawdza, czy klucz jest naprawdę akceptowany.
  Wymaga sieci.

```bash
omi auth status    # kontrola lokalna, offline
omi auth whoami    # kontrola na serwerze
```

Odśwież wygasający token bez ponownego logowania — to polecenie dotyczy
**tylko sesji przeglądarki/OAuth**. Dla profilu uwierzytelnionego kluczem API
(`omi_dev_*`) `omi auth refresh` kończy się błędem użycia (kod 1): nie ma tokenu
do odświeżenia — w razie potrzeby zmień klucz w aplikacji internetowej Omi:

```bash
omi auth refresh
```

Wylogowanie:

```bash
omi auth logout
```

---

## 3. Podstawowe polecenia

### Wspomnienia (memories)

Fakty i wiedza, które system zapamiętał o Tobie.

```bash
# lista wspomnień
omi memory list

# utwórz nowe
omi memory create "Użytkownik preferuje ciemny motyw" --category lifestyle

# wyświetl konkretne
omi memory get <MEMORY_ID>
```

### Rozmowy (conversations)

Historia głosu i tekstu z urządzenia lub aplikacji.

```bash
# 5 najnowszych rozmów
omi conversation list --limit 5

# pełna rozmowa z transkrypcją
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Elementy działań (action items)

Zadania, które Omi wywnioskował z rozmów.

```bash
# tylko otwarte
omi action-item list --open

# oznacz jako ukończone
omi action-item complete <ACTION_ITEM_ID>
```

### Cele (goals)

```bash
# lista celów
omi goal list

# zapisz nową wartość postępu (wymaga OBU argumentów: cel i wartość)
omi goal progress <GOAL_ID> 25

# historia zmian
omi goal history <GOAL_ID>
```

---

## Pytania w języku naturalnym (`ask`)

Osobne polecenie najwyższego poziomu: przyjmuje pytanie w języku naturalnym,
a odpowiedź buduje na podstawie Twoich rozmów.

```bash
omi ask "co zdecydowałem w sprawie przeprowadzki"
omi --json ask "jakie elementy działań obiecałem ukończyć w tym tygodniu"
```

---

## 4. JSON i skrypty (`--json`)

`omi-cli` może produkować JSON czytelny dla maszyny. Opcja `--json` jest
**globalna** i musi być umieszczona **przed** podpoleceniem.

```bash
# wspomnienia: wyodrębnij id, tekst i kategorię
omi --json memory list | jq '.[] | {id, content, category}'

# tytuły ostatnich rozmów
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# otwarte elementy działań
omi --json action-item list --open | jq '.'
```

> **Częsty błąd.** `--json` stoi przed podpoleceniem, a nie po.
> * Poprawnie: `omi --json memory list`
> * Błędnie: `omi memory list --json`

W trybie `--json` znikają komunikaty o postępie i spinnery dla ludzi —
stdout zawiera tylko jeden prawidłowy dokument JSON. Błędy trafiają do stderr
w postaci `{"error": "...", "detail": "..."}`.

---

## 5. Kody wyjścia

Stabilne kody wyjścia do rozgałęziania w skryptach.

| Kod | Znaczenie |
| :--- | :--- |
| `0` | Sukces |
| `1` | Błąd użycia (zła flaga, brak wymaganego argumentu) |
| `2` | Uwierzytelnianie nieudane — wymagane logowanie |
| `3` | Błąd serwera/sieci |
| `4` | Limit szybkości — spróbuj ponownie później |
| `5` | Zasób nie znaleziony |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "tego wspomnienia nie ma" ;;
    *) echo "błąd $code" ;;
  esac
fi
```

---

## 6. Profile i konfiguracja

Jeśli masz wiele kont lub środowisk, rozdziel je profilami.
Ustawienia są zapisywane w `~/.omi/config.toml`.

```bash
# logowanie do profilu osobistego
omi --profile personal auth login

# logowanie do profilu służbowego
omi --profile work auth login

# uruchom polecenie w konkretnym profilu
omi --profile work memory list
```

Używany profil określa się w tej kolejności: opcja `--profile` (lub `-p`)
ma pierwszeństwo przed wszystkim; następnie zmienna środowiskowa `OMI_PROFILE`;
następnie aktywny profil w `~/.omi/config.toml`; a na końcu profil `default` jako rezerwa.

Zobacz i zmień samą konfigurację:

```bash
# co jest teraz ustawione
omi config show

# gdzie jest plik konfiguracyjny
omi config path

# zmień wartość
omi config set api_base https://api.omi.me
```

---

## 7. Następne kroki

* [`agent_quickstart.md`](./agent_quickstart.md) — jak podłączyć `omi-cli` do agenta AI.
* [`shell_examples.sh`](./shell_examples.sh) — gotowe przykłady dla powłoki.
* [Dokumentacja Omi](https://docs.omi.me/doc/developer/cli/introduction) — pełna referencja poleceń.
