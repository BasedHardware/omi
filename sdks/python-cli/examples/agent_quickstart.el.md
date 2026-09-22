# omi-cli για agents

> Πρακτικός οδηγός για LLM-driven harnesses (Claude Code, Cursor, τα δικά σου bots).

## Γιατί το CLI είναι φιλικό προς agents

* **Σταθερή συμβολοσειρά JSON.** Το `--json` εξάγει έγκυρο έγγραφο JSON στο stdout και
  *μόνο* έγγραφο JSON — χωρίς μηνύματα προόδου, χωρίς spinners. Τα σφάλματα πηγαίνουν στο
  stderr ως `{"error": "...", "detail": "..."}`.
* **Σταθεροί κωδικοί εξόδου.** `0` ok / `1` χρήση / `2` auth / `3` server / `4`
  όριο ρυθμού / `5` δεν βρέθηκε. Τα agents μπορούν να διακλαδίζουν πάνω σε αυτούς
  χωρίς να αναλύουν σφάλματα σε φυσική γλώσσα.
* **Χωρίς διαδραστικά prompts σε headless περιβάλλοντα.** Πέρασε `--yes` (ή `-y`) σε
  καταστροφικές εντολές· πέρασε `--api-key` ή ορίσε `OMI_API_KEY` για να παραλείψεις
  διαδραστικό login.
* **Συγχωρητική συμπεριφορά επανάληψης.** Τα `429` και `5xx` επαναλαμβάνονται με backoff
  πριν εμφανιστούν.

## Auth (μία φορά, από τον άνθρωπο)

Ο χρήστης παίρνει ένα dev API key από την Omi web app
(`https://app.omi.me` → Developer → API Keys) και είτε:

```bash
omi auth login                          # interactive paste; key not in shell history
# or
export OMI_API_KEY=omi_dev_...          # ephemeral, container-friendly
```

## Τα πέντε πράγματα που κάνουν συχνά τα agents

### 1. Διάβασμα μνημών

```bash
omi memory list --json --limit 50 | jq '.[] | {id, content, category}'
```

### 2. Δημιουργία μνήμης

```bash
omi memory create --json "User prefers dark mode" --category lifestyle
```

### 3. Διάβασμα συνομιλιών

```bash
omi conversation list --json --limit 5 \
  | jq '.[] | {id, title: .structured.title, started_at}'
```

### 4. Διάβασμα ανοιχτών action items

```bash
omi action-item list --json --open
```

### 5. Ολοκλήρωση ενός action item

```bash
omi action-item complete --json a1b2c3d4
```

## Τοπική API Desktop

Όταν το Omi Desktop εκθέτει την τοπική του API, τα agents μπορούν να ρωτήσουν
ιστορικό οθόνης συσκευής, recaps, SQL και εργασίες χωρίς να χρησιμοποιήσουν την
cloud dev API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# or, for ephemeral sessions:
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

Ολοκλήρωνε ή διέγραφε εργασίες μόνο όταν ο χρήστης το ζητά καθαρά:

```bash
omi --json local task complete task_123
omi --json local task delete task_123 --yes
```

Το `omi local screenshot SCREENSHOT_ID --output PATH` γράφει το screenshot στο
δίσκο και εξακολουθεί να εκτυπώνει JSON στο stdout για scripts. Το screenshot ID
συνήθως έρχεται από το `local search-screen` ή SQL πάνω στον πίνακα `screenshots`.
Αν το Desktop επιστρέψει δομημένη αποτυχία όπως `screenshot_pending`,
`screenshot_file_missing`, ή `screenshot_chunk_corrupted`, η JSON mode διατηρεί
τα πεδία `reason`, `hint`, και `screenshot_id` στο stderr ώστε τα agents να
μπορούν να δοκιμάσουν παλιότερο ID ή να αναφέρουν το ακριβές εμπόδιο.
Επιβεβαίωνε τις επιτυχείς εξόδους με `file PATH` πριν τις περάσεις σε vision tools.

## Παράδειγμα: Python agent loop

```python
import json
import subprocess
from typing import Any

def omi(*args: str) -> Any:
    """Invoke the omi CLI in JSON mode, raising on non-success exit codes."""
    result = subprocess.run(
        ["omi", "--json", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # The CLI prints structured errors to stderr in JSON mode:
        # {"error": "...", "detail": "..."}
        try:
            err = json.loads(result.stderr)
        except json.JSONDecodeError:
            err = {"error": result.stderr.strip()}
        raise RuntimeError(f"omi exited {result.returncode}: {err}")
    return json.loads(result.stdout) if result.stdout.strip() else None

# Read all open action items and mark anything older than 30 days complete.
from datetime import datetime, timedelta, timezone

cutoff = datetime.now(timezone.utc) - timedelta(days=30)
items = omi("action-item", "list", "--open")
for item in items or []:
    created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    if created < cutoff:
        omi("action-item", "complete", item["id"])
```

## Διαχείριση ορίων ρυθμού

Μνήμες: 120/ώρα. Συνομιλίες: 25/ώρα. Ομαδικές δημιουργίες: 15/ώρα.

```python
result = subprocess.run(["omi", "--json", "memory", "create", text], capture_output=True, text=True)
if result.returncode == 4:                             # rate limited
    err = json.loads(result.stderr)
    # err["detail"] looks like: "Retry in 12s. ..."
    time.sleep(parse_retry_window(err["detail"]) or 60)
```

## Συμβουλές

* Χρησιμοποίησε `--profile <name>` αν το agent διαχειρίζεται πολλούς λογαριασμούς Omi.
  Κάθε profile έχει τα δικά του credentials και API base.
* Χρησιμοποίησε `--api-base http://localhost:8080` για τοπική δοκιμή backend.
* Χρησιμοποίησε `OMI_LOCAL_API_URL` και `OMI_LOCAL_TOKEN` για να παρακάμψεις τις
  ρυθμίσεις τοπικής Desktop API ενός profile για μία εκτέλεση.
* Χρησιμοποίησε `--verbose` για debug — καταγράφει `METHOD path → status (Ns)` στο stderr
  χωρίς να επηρεάζει το stdout, ώστε η JSON mode να παραμένει έγκυρη.
* Για piping περιεχομένου σε μια συνομιλία, χρησιμοποίησε `--text -`:
  ```bash
  cat meeting_notes.md | omi conversation create --text - --text-source other_text
  ```
