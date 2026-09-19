# omi-cli για πράκτορες

> Πρακτικός οδηγός για περιβάλλοντα βασισμένα σε LLM (Claude Code, Cursor, δικά σας bots).

## Γιατί το CLI είναι φιλικό προς τους πράκτορες

* **Σταθερή σύμβαση JSON.** Η επιλογή `--json` εξάγει ένα έγκυρο έγγραφο JSON στο stdout και *μόνο* ένα έγγραφο JSON — χωρίς μηνύματα προόδου, χωρίς γραφικά φόρτωσης. Τα σφάλματα κατευθύνονται στο stderr ως `{"error": "...", "detail": "..."}`.
* **Σταθεροί κωδικοί εξόδου.** `0` εντάξει / `1` σφάλμα χρήσης / `2` σφάλμα ελέγχου ταυτότητας / `3` σφάλμα διακομιστή / `4` όριο ρυθμού αιτημάτων / `5` δεν βρέθηκε. Οι πράκτορες μπορούν να διακλαδώνονται βάσει αυτών χωρίς να αναλύουν μηνύματα φυσικής γλώσσας.
* **Χωρίς διαδραστικές ερωτήσεις σε αυτόνομα περιβάλλοντα.** Προσθέστε `--yes` (ή `-y`) σε καταστροφικές εντολές. Περάστε `--api-key` ή ορίστε το `OMI_API_KEY` για να παραλείψετε τη διαδραστική σύνδεση.
* **Επιεικής συμπεριφορά επανάληψης.** Τα σφάλματα `429` και `5xx` επαναλαμβάνονται αυτόματα με εκθετική καθυστέρηση πριν εμφανιστούν.

## Έλεγχος ταυτότητας (άπαξ, από τον άνθρωπο)

Ο χρήστης αποκτά ένα κλειδί API προγραμματιστή από την εφαρμογή Omi web (`https://app.omi.me` → Developer → API Keys) και επιλέγει ένα από τα δύο:

```bash
omi auth login                          # διαδραστική επικόλληση. Το κλειδί δεν παραμένει στο ιστορικό του κελύφους
# ή
export OMI_API_KEY=omi_dev_...          # προσωρινό, κατάλληλο για containers
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

### 4. Ανάγνωση εκκρεμών εργασιών

```bash
omi action-item list --json --open
```

### 5. Σήμανση εργασίας ως ολοκληρωμένης

```bash
omi action-item complete --json a1b2c3d4
```

## Τοπικό Desktop API

Όταν το Omi Desktop εκθέτει το τοπικό του API, οι πράκτορες μπορούν να αναζητούν ιστορικό οθόνης στη συσκευή, ανακεφαλαιώσεις, SQL και εργασίες χωρίς να χρησιμοποιούν το dev API cloud:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ή, για προσωρινές συνεδρίες:
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

Ολοκληρώνετε ή διαγράφετε εργασίες μόνο όταν ο χρήστης το ζητά ρητά:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Η εντολή `omi local screenshot SCREENSHOT_ID --output PATH` αποθηκεύει το στιγμιότυπο οθόνης στον δίσκο και εξακολουθεί να εξάγει JSON στο stdout για σενάρια. Το αναγνωριστικό στιγμιοτύπου προέρχεται συνήθως από το `local search-screen` ή από SQL ερώτημα στον πίνακα `screenshots`. Εάν το Desktop επιστρέψει δομημένο σφάλμα όπως `screenshot_pending`, `screenshot_file_missing` ή `screenshot_chunk_corrupted`, η λειτουργία JSON διατηρεί τα πεδία `reason`, `hint` και `screenshot_id` στο stderr, επιτρέποντας στους πράκτορες να δοκιμάσουν ξανά με παλαιότερο ID ή να αναφέρουν το ακριβές πρόβλημα. Επαληθεύστε τα επιτυχή αρχεία με `file PATH` πριν τα προωθήσετε σε εργαλεία όρασης.

## Πρακτικό παράδειγμα: Βρόχος πράκτορα σε Python

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Καλεί το omi CLI σε λειτουργία JSON, εγείροντας εξαίρεση σε μη μηδενικούς κωδικούς εξόδου."""
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
        raise RuntimeError(f"το omi τερματίστηκε με κωδικό {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Ανάγνωση όλων των εκκρεμών εργασιών και ολοκλήρωση όσων είναι παλαιότερες από 30 ημέρες.
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
if result.returncode == 4:                             # όριο ρυθμού αιτημάτων
    err = json.loads(result.stderr)
    # το err["detail"] μοιάζει με: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Συμβουλές

* Χρησιμοποιήστε `--profile <όνομα>` εάν ο πράκτοράς σας διαχειρίζεται πολλούς λογαριασμούς Omi. Κάθε προφίλ έχει τα δικά του διαπιστευτήρια και βάση API.
* Χρησιμοποιήστε `--api-base http://localhost:8080` για τοπικές δοκιμές backend.
* Χρησιμοποιήστε τα `OMI_LOCAL_API_URL` και `OMI_LOCAL_TOKEN` για να παρακάμψετε τις τοπικές ρυθμίσεις Desktop API για μία εκτέλεση.
* Χρησιμοποιήστε `--verbose` για εντοπισμό σφαλμάτων — καταγράφει `METHOD path → status (Ns)` στο stderr χωρίς να επηρεάζει το stdout, διατηρώντας έγκυρη τη λειτουργία JSON.
* Για διοχέτευση περιεχομένου σε μια συνομιλία μέσω pipe, χρησιμοποιήστε `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
