# omi-cli για πράκτορες

> Πρακτικός οδηγός για περιβάλλοντα που καθοδηγούνται από LLM (Claude Code, Cursor, δικά σας bots).

## Γιατί το CLI είναι φιλικό προς τους πράκτορες

* **Σταθερό συμβόλαιο JSON.** Το `--json` εξάγει ένα έγκυρο έγγραφο JSON στο stdout και
  *μόνο* ένα έγγραφο JSON — χωρίς μηνύματα προόδου, χωρίς spinners. Τα σφάλματα πηγαίνουν στο
  stderr ως `{"error": "...", "detail": "..."}`.
* **Σταθεροί κωδικοί εξόδου.** `0` επιτυχία / `1` χρήση / `2` αυθεντικοποίηση / `3` διακομιστής / `4` όριο
  ρυθμού / `5` δεν βρέθηκε. Οι πράκτορες μπορούν να διακλαδώνονται βάσει αυτών χωρίς να αναλύουν
  σφάλματα φυσικής γλώσσας.
* **Καμία διαδραστική προτροπή σε περιβάλλοντα χωρίς διεπαφή χρήστη (headless).** Περάστε `--yes` (ή `-y`) σε
  καταστροφικές εντολές· περάστε `--api-key` ή ορίστε το `OMI_API_KEY` για να παραλείψετε
  τη διαδραστική σύνδεση.
* **Ανεκτική συμπεριφορά επανάληψης.** Τα `429` και `5xx` επανεκτελούνται αυτόματα με backoff
  πριν εμφανιστούν.

## Αυθεντικοποίηση (εφάπαξ, από τον άνθρωπο)

Ο χρήστης λαμβάνει ένα dev API key από την εφαρμογή ιστού Omi
(`https://app.omi.me` → Developer → API Keys) και επιλέγει ένα από τα δύο:

```bash
omi auth login                          # διαδραστική επικόλληση· το κλειδί δεν αποθηκεύεται στο ιστορικό του shell
# ή
export OMI_API_KEY=omi_dev_...          # εφήμερο, φιλικό προς containers
```

## Τα πέντε πράγματα που κάνουν συχνότερα οι πράκτορες

### 1. Ανάγνωση αναμνήσεων

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Δημιουργία ανάμνησης

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Ανάγνωση συνομιλιών

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Ανάγνωση ανοιχτών στοιχείων δράσης

```bash
omi action-item list --json --open
```

### 5. Σήμανση ενός στοιχείου δράσης ως ολοκληρωμένου

```bash
omi action-item complete --json a1b2c3d4
```

## Τοπικό Desktop API

Όταν το Omi Desktop εκθέτει το τοπικό του API, οι πράκτορες μπορούν να αναζητούν ιστορικό
οθόνης στη συσκευή, ανακεφαλαιώσεις, SQL και εργασίες χωρίς να χρησιμοποιούν το cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ή για εφήμερες συνεδρίες:
export OMI_LOCAL_API_URL=http://127.0.0.1:47778
export OMI_LOCAL_TOKEN=...

omi --json local status
omi --json local tools
omi --json local call search_screen_history --args-json '{"query":"pricing page","days":7}'
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local sql "SELECT COUNT(*) AS screenshots FROM screenshots"
omi --json local task search "taxes" --include-completed
```

Ολοκληρώστε ή διαγράψτε εργασίες μόνο όταν το ζητήσει ρητά ο χρήστης:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Το `omi local screenshot SCREENSHOT_ID --output PATH` αποθηκεύει το στιγμιότυπο οθόνης στον
δίσκο και εξακολουθεί να εκτυπώνει JSON στο stdout για scripts. Το αναγνωριστικό στιγμιοτύπου συνήθως
προέρχεται από το `local search-screen` ή από SQL στον πίνακα `screenshots`. Εάν το Desktop
επιστρέψει μια δομημένη αποτυχία όπως `screenshot_pending`, `screenshot_file_missing`
ή `screenshot_chunk_corrupted`, η λειτουργία JSON διατηρεί τα πεδία `reason`, `hint` και
`screenshot_id` στο stderr, ώστε οι πράκτορες να μπορούν να δοκιμάσουν ξανά με παλαιότερο ID ή να αναφέρουν το
ακριβές εμπόδιο. Επαληθεύστε τις επιτυχείς εξόδους με την εντολή `file PATH` πριν τις παραδώσετε
σε εργαλεία όρασης (vision tools).

## Ολοκληρωμένο παράδειγμα: βρόχος πράκτορα σε Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Εκτελεί το omi CLI σε λειτουργία JSON, εγείροντας σφάλμα σε μη μηδενικό κωδικό εξόδου."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Το CLI εκτυπώνει δομημένα σφάλματα στο stderr σε λειτουργία JSON:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ανάγνωση όλων των ανοιχτών στοιχείων δράσης και σήμανση όσων είναι παλαιότερα των 30 ημερών ως ολοκληρωμένα.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Διαχείριση ορίων ρυθμού αιτημάτων

Αναμνήσεις: 120/ώρα. Συνομιλίες: 25/ώρα. Μαζική δημιουργία: 15/ώρα.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # υπέρβαση ορίου ρυθμού
    err = json.loads(result.stderr)
    # Το err["detail"] μοιάζει με: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Συμβουλές

* Χρησιμοποιήστε `--profile <name>` εάν ο πράκτοράς σας διαχειρίζεται πολλούς λογαριασμούς Omi.
  Κάθε προφίλ έχει τα δικά του διαπιστευτήρια και βασικό URL API.
* Χρησιμοποιήστε `--api-base http://localhost:8080` για δοκιμές σε τοπικό backend.
* Χρησιμοποιήστε τα `OMI_LOCAL_API_URL` και `OMI_LOCAL_TOKEN` για να αντικαταστήσετε τις τοπικές
  ρυθμίσεις Desktop API ενός προφίλ για μία εκτέλεση.
* Χρησιμοποιήστε `--verbose` για εντοπισμό σφαλμάτων — καταγράφει `METHOD path → status (Ns)` στο stderr
  χωρίς να επηρεάζει το stdout, διατηρώντας έγκυρη τη λειτουργία JSON.
* Για διοχέτευση περιεχομένου σε μια συνομιλία, χρησιμοποιήστε το `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
