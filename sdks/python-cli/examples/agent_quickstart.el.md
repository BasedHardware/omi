# omi-cli για agents

> Πρακτικός οδηγός για περιβάλλοντα που βασίζονται σε LLM (Claude Code, Cursor, δικά σας bots).

## Γιατί το CLI είναι φιλικό προς τους agents

* **Σταθερό συμβόλαιο JSON.** Η σημαία `--json` εκπέμπει ένα έγκυρο έγγραφο JSON στο stdout και *αποκλειστικά* ένα έγγραφο JSON — χωρίς μηνύματα προόδου, χωρίς spinners. Τα σφάλματα κατευθύνονται στο stderr ως `{"error": "...", "detail": "..."}`.
* **Σταθεροί κωδικοί εξόδου.** `0` ok / `1` σφάλμα χρήσης / `2` σφάλμα πιστοποίησης / `3` σφάλμα διακομιστή / `4` υπέρβαση ορίου / `5` δεν βρέθηκε. Οι agents μπορούν να εκτελούν διακλαδώσεις χωρίς να αναλύουν μηνύματα φυσικής γλώσσας.
* **Χωρίς διαδραστικές ερωτήσεις σε headless περιβάλλον.** Χρησιμοποιήστε `--yes` (ή `-y`) για καταστροφικές εντολές. Χρησιμοποιήστε `--api-key` ή ορίστε το `OMI_API_KEY` για παράκαμψη της διαδραστικής σύνδεσης.
* **Ευέλικτη συμπεριφορά επαναπροσπάθειας.** Τα σφάλματα `429` και `5xx` επαναλαμβάνονται αυτόματα με backoff πριν εμφανιστεί σφάλμα.

## Έλεγχος ταυτότητας (εφάπαξ, από τον άνθρωπο)

Ο χρήστης αποκτά ένα dev API key από την εφαρμογή web του Omi
(`https://app.omi.me` → Developer → API Keys) και επιλέγει:

```bash
omi auth login                          # διαδραστική επικόλληση; το κλειδί δεν αποθηκεύεται στο ιστορικό
# ή
export OMI_API_KEY=omi_dev_...          # εφήμερο, κατάλληλο για containers
```

## Οι πέντε κύριες ενέργειες των agents

### 1. Ανάγνωση αναμνήσεων (memories)

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

### 4. Ανάγνωση εκκρεμών εργασιών (action items)

```bash
omi action-item list --json --open
```

### 5. Σήμανση εργασίας ως ολοκληρωμένης

```bash
omi action-item complete --json a1b2c3d4
```

## Τοπικό API επιφάνειας εργασίας (Local Desktop API)

Όταν το Omi Desktop εκθέτει το τοπικό του API, οι agents μπορούν να εκτελούν ερωτήματα στο ιστορικό οθόνης της συσκευής, ανακεφαλαιώσεις, SQL και εργασίες χωρίς το cloud API:

```bash
omi local configure --url http://127.0.0.1:47778 --token ...
# ή, για εφήμερες συνεδρίες:
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
omi --json local task complete task_1
```
