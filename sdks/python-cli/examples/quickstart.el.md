# Οδηγός Γρήγορης Εκκίνησης omi-cli

## Εγκατάσταση

```bash
pip install omi-cli
```

## Σύνδεση

```bash
omi auth login
```

Το πρόγραμμα περιήγησης θα ανοίξει για να συνδεθείτε με τον λογαριασμό σας.

## Βασικές Εντολές

### Προβολή λίστας συνομιλιών

```bash
omi conversation list
```

### Προβολή συγκεκριμένης συνομιλίας

```bash
omi conversation get <αναγνωριστικό_συνομιλίας>
```

### Αναζήτηση συνομιλιών

```bash
# omi conversation list (search filters)
omi conversation list "όρος αναζήτησης"
```

## Προηγμένες Επιλογές

### Φιλτράρισμα βάσει ορίου

```bash
omi conversation list --limit 10
```

### Συμπερίληψη απομαγνητοφωνήσεων

```bash
omi conversation list --include-transcript
```

### Εξαγωγή σε μορφή JSON

```bash
omi --json conversation list
```

### Σελιδοποίηση

```bash
omi conversation list --limit 50 --offset 100
```

## Αποσύνδεση

```bash
omi auth logout
```

## Βοήθεια

```bash
omi --help
omi conversation --help
```

## Πόροι

- [Τεκμηρίωση](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
