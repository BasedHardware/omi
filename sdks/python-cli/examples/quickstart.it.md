# Guida Rapida di omi-cli (Italian Quickstart)

Guida di riferimento pratico per l'interfaccia a riga di comando ufficiale di Omi (`omi-cli`).
Questo documento illustra l'installazione, l'autenticazione, i comandi principali per la gestione dei dati e le tecniche di automazione per script e agenti autonomi.

---

## Panoramica ed Eseguibile

* **Nome pacchetto PyPI:** `omi-cli`
* **File binario eseguibile:** `omi`

Per evitare confusione durante l'installazione e l'uso:

```bash
# Si installa con il nome del pacchetto:
pipx install omi-cli

# Si esegue usando il comando abbreviato:
omi --help
```

---

## Installazione

Si consiglia l'uso di `pipx` per installare la CLI in un ambiente virtuale isolato senza conflitti di dipendenze con Python globale.

### Metodo Consigliato (`pipx`)

```bash
pipx install omi-cli
```

Per aggiornare all'ultima versione disponibile:

```bash
pipx upgrade omi-cli
```

### Metodo Alternativo (`pip`)

```bash
pip install --user omi-cli
```

Verificare che l'installazione sia avvenuta correttamente:

```bash
omi --version
```

---

## Autenticazione

La CLI supporta tre modalita principali di autenticazione: accesso interattivo tramite browser, chiave API statica e variabile d'ambiente.

### 1. Accesso Interattivo via Browser

Ideale per computer di sviluppo con interfaccia grafica:

```bash
omi auth login --browser
```

Il comando aprira la finestra di autenticazione Web e memorizzera il token in modo sicuro sul sistema locale.

### 2. Accesso Diretto con Chiave API (Headless)

Adatto per server remoti, connessioni SSH o ambienti CI/CD:

```bash
omi auth login --api-key
```

La CLI richiederà di incollare la chiave generata nella dashboard sviluppatore di Omi.

### 3. Variabile d'Ambiente

Per container Docker o pipeline automatizzate senza memorizzazione di file:

```bash
export OMI_API_KEY="tua-chiave-api-segreta"
```

### Verifica dell'Autenticazione

* **Verifica offline (stato locale del token):**
  ```bash
  omi auth status
  ```
* **Verifica online (convalida in tempo reale sul server):**
  ```bash
  omi auth whoami
  ```

Per disconnettere la sessione locale:

```bash
omi auth logout
```

---

## Flussi di Lavoro Principali

### Memorie (`omi memory`)

Le memorie rappresentano elementi atomici di contesto catturati da Omi.

```bash
# Elenco delle memorie recenti
omi memory list --limit 10

# Creazione manuale di una nuova memoria
omi memory create --text "Riunione di progetto fissata per martedi alle 10:00 con il team tecnico."

# Ricerca semantica nel database delle memorie
omi memory search "riunione di progetto"
```

### Conversazioni (`omi conversation`)

Gestione dei dialoghi e delle trascrizioni audio registrate.

```bash
# Elenco conversazioni
omi conversation list --limit 5

# Dettagli di una conversazione specifica
omi conversation get conv_123456

# Esportazione della trascrizione completa in formato Markdown
omi conversation export conv_123456 --format markdown > trascrizione.md
```

### Attivita e Azioni (`omi action-item`)

Compiti e impegni estratti automaticamente dai dialoghi.

```bash
# Elenco compiti da completare
omi action-item list --status pending

# Segnare un compito come completato
omi action-item update act_789012 --completed
```

### Obiettivi (`omi goal`)

Monitoraggio degli obiettivi personali e professionali a lungo termine.

```bash
# Visualizzazione obiettivi attivi
omi goal list

# Creazione di un nuovo obiettivo
omi goal create --title "Completare la documentazione multilingue" --horizon month

# Aggiornamento percentuale di progresso
omi goal update goal_345678 --progress 75
```

---

## Automazione Strutturata (`--json` & `jq`)

Ogni comando `omi` accetta l'argomento globale `--json`, garantendo output leggibili direttamente da macchine e parser.

### Estrarre ID e Contenuti con `jq`

```bash
# Estrarre tutti i testi delle memorie
omi --json memory list --limit 20 | jq -r '.[].content'

# Trovare i compiti prioritari non completati
omi --json action-item list | jq '.[] | select(.completed == false) | {id: .id, description: .description}'
```

---

## Tabella dei Codici di Uscita (Exit Codes)

La CLI adotta codici di uscita deterministici, consentendo agli script di gestire gli errori con precisione:

| Codice | Significato | Causa Tipica |
| :---: | :--- | :--- |
| `0` | **Successo** | Operazione completata correttamente. |
| `1` | **Errore Generico** | Eccezione interna non gestita o errore imprevisto. |
| `2` | **Errore Argomenti** | Flag sconosciuti, parametri mancanti o sintassi errata. |
| `3` | **Non Autenticato** | Token assente, scaduto o chiave API non valida. |
| `4` | **Non Trovato** | La risorsa (memoria, conversazione, obiettivo) non esiste. |
| `5` | **Errore di Rete** | Connessione interrotta o timeout dell'endpoint remoto. |

---

## Snippet Multi-Piattaforma

### Bash / Zsh (Linux & macOS)

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Verifica credenziali Omi..."
if ! omi auth status > /dev/null 2>&1; then
    echo "Errore: autenticazione richiesta. Esegui 'omi auth login'." >&2
    exit 3
fi

echo "Salvataggio nuova nota..."
omi memory create --text "Controllo automatico completato con successo."
```

### PowerShell (Windows)

```powershell
Write-Host "Verifica credenziali Omi..."
omi auth status
if ($LASTEXITCODE -ne 0) {
    Write-Error "Autenticazione mancante. Esegui 'omi auth login'."
    exit $LASTEXITCODE
}

Write-Host "Recupero obiettivi..."
omi --json goal list | ConvertFrom-Json | ForEach-Object {
    [PSCustomObject]@{
        Id = $_.id
        Titolo = $_.title
        Progresso = "$($_.progress)%"
    }
}
```

---

## Integrazione Omi Desktop Locale

Se l'applicazione Omi Desktop e in esecuzione localmente, la CLI puo interagire con i suoi servizi di contesto locale:

```bash
# Configurare la porta locale dell'applicazione
omi local configure --port 8000

# Cercare testo sullo schermo catturato localmente
omi local search-screen "rapporto trimestrale"
```

---

## Gestione Profili Multi-Ambiente

E possibile configurare profili distinti (ad esempio sviluppo, collaudo e produzione) tramite `--profile` o configurazione in `~/.omi/config.toml`:

```bash
# Utilizzare un profilo specifico
omi --profile lavoro memory list

# Specificare un differente endpoint di prova
omi --profile staging --api-url https://api-staging.omi.me memory list
```

---

## Sicurezza e Buone Pratiche

1. **Protezione dei Token:** Non includere mai token di accesso o chiavi API in repository Git pubblici.
2. **Cronologia Shell:** Quando si usa `--api-key` in ambienti condivisi, evitare di passare la chiave direttamente come argomento inline; preferire l'immissione interattiva mascherata o la variabile d'ambiente `OMI_API_KEY`.
3. **Controllo dei Permessi:** In ambienti di produzione Unix, verificare che la directory di configurazione `~/.omi/` abbia permessi restrittivi (`chmod 700 ~/.omi`).
