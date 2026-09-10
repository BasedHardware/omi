# Guida di Avvio Rapido di omi-cli (Italian Quickstart)

> Guida pratica per interagire con Omi direttamente dal terminale — progettata per sviluppatori e agenti AI autonomi.

`omi-cli` è l'interfaccia a riga di comando ufficiale per l'API sviluppatori di [Omi](https://omi.me). Consente di gestire in modo strutturato e automatizzabile le quattro risorse fondamentali del sistema: memorie (memories), conversazioni (conversations), attività (action items) e obiettivi (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentazione Ufficiale:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Codice Sorgente:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installazione

Il metodo consigliato è l'uso di `pipx`, che isola le dipendenze dall'ambiente di sistema:

```bash
# Consigliato: installazione isolata con pipx
pipx install omi-cli

# In alternativa tramite pip tradizionale
pip install omi-cli
```

> **Attenzione: Nome del pacchetto vs. Nome del comando**
> * Il nome del pacchetto su PyPI è **`omi-cli`** (il nome `omi` appartiene a un altro pacchetto non correlato).
> * Il comando eseguibile nel terminale è semplicemente **`omi`**.

Verificare l'installazione consultando la versione e il menu di aiuto:

```bash
omi --version
omi --help
```

---

## 2. Autenticazione (Authentication)

`omi-cli` supporta due metodi di autenticazione:

| Metodo | Indicato per | Esempio di utilizzo |
| :--- | :--- | :--- |
| **Chiave API (`omi_dev_*`)** | Automazioni, CI/CD, server headless, agenti AI | `omi auth login --api-key ...` o `OMI_API_KEY` |
| **OAuth via Browser (Google/Apple)** | Sviluppatori su laptop / workstation locali | `omi auth login --browser` (Google) / `--provider apple` |

### Login Interattivo
Se eseguito senza opzioni aggiuntive, la procedura guidata chiede quale flusso utilizzare:

```bash
omi auth login
# 1) Browser — autenticazione via Google (usa `--provider apple` per Apple)
# 2) API key — Incolla la tua chiave sviluppatore generata su app.omi.me
```

### Login Diretto dal Browser
```bash
# Login predefinito tramite Google
omi auth login --browser

# In alternativa tramite Apple
omi auth login --browser --provider apple
```

### Utilizzo di una Chiave Sviluppatore (API Key)
Generare la chiave nel pannello di [app.omi.me](https://app.omi.me) sotto **Developer → API Keys**:

```bash
# Salvare nel profilo locale tramite riga di comando
omi auth login --api-key omi_dev_...

# Oppure impostare come variabile d'ambiente (ideale per container e pipeline CI/CD)
# Nota: se il profilo locale ha già una chiave memorizzata, eseguire prima `omi auth logout`.
export OMI_API_KEY="omi_dev_your_actual_key_here"
```

### Verifica dello Stato di Autenticazione
* `omi auth status`: Mostra il profilo locale attivo e la credenziale mascherata; la data di scadenza viene indicata solo per i profili OAuth (funziona offline).
* `omi auth whoami`: Invia una richiesta all'API Omi per confermare la validità delle credenziali in tempo reale (richiede connessione).

```bash
omi auth status
omi auth whoami
```

Per terminare la sessione:
```bash
omi auth logout
# Se OMI_API_KEY è impostata nell'ambiente, rimuoverla dalla sessione (Bash/Zsh: `unset OMI_API_KEY`).
```

---

## 3. Comandi Principali

### Memorie (Memories)
Fatti, note e informazioni di contesto acquisite da Omi:

```bash
# Elenco delle memorie salvate
omi memory list

# Creazione di una nuova memoria
omi memory create "Preferisce risposte tecniche concise con esempi in Python" --category work

# Dettagli di una specifica memoria
omi memory get <MEMORY_ID>
```

### Conversazioni (Conversations)
Cronologia audio e trascrizioni registrate dai dispositivi Omi:

```bash
# Elenco delle 5 conversazioni più recenti
omi conversation list --limit 5

# Dettagli e trascrizione completa della conversazione
omi conversation get <CONVERSATION_ID> --include-transcript

# Esportazione della trascrizione completa in formato JSON
omi --json conversation get <CONVERSATION_ID> --include-transcript > trascrizione.json
```

### Attività e Impegni (Action Items)
Compiti e promemoria estratti automaticamente dai dialoghi:

```bash
# Elenco delle attività aperte
omi action-item list --open

# Completamento di un'attività
omi action-item complete <ACTION_ITEM_ID>
```

### Obiettivi (Goals)
Monitoraggio degli obiettivi e delle metriche di progresso:

```bash
# Elenco degli obiettivi attivi
omi goal list

# Creazione di un nuovo obiettivo quantitativo
omi goal create "Bere 2L di acqua al giorno" --type numeric --target 2 --unit liters
```

---

## 4. Automazione e Output in JSON (`--json`)

`omi-cli` include il supporto nativo di primo livello per pipeline di elaborazione dati. Specificando il flag globale `--json`, i risultati vengono restituiti in formato JSON valido:

```bash
# Elenco memorie in JSON ed estrazione campi con jq
omi --json memory list | jq '.[] | {id, content, category}'

# Estrazione dei titoli delle ultime conversazioni
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Consultazione delle attività aperte in formato grezzo
omi --json action-item list --open | jq '.'
```

> **Regola di sintassi essenziale:**
> `--json` è un'**opzione globale** e deve precedere il sottocomando:
> * Corretto: `omi --json memory list`
> * Errato: `omi memory list --json`

---

## 5. Codici di Uscita (Exit Codes)

Per garantire un'integrazione affidabile in script shell e flussi CI/CD:

| Codice | Significato | Descrizione |
| :---: | :--- | :--- |
| `0` | **Successo (Success)** | Esecuzione completata correttamente. |
| `1` | **Errore di Uso (Validazione Applicazione)** | Dati non validi o errore di validazione dell'applicazione; gli errori di sintassi del parser Click restituiscono codice `2`. |
| `2` | **Errore di Autenticazione / Sintassi CLI** | Mancata autenticazione, token scaduto o flag di sintassi non riconosciuti dal parser Click. |
| `3` | **Errore del Server / Rete (Server Error)** | Risposta HTTP 5xx, timeout o connessione non raggiungibile. |
| `4` | **Limite di Richieste (Rate Limited)** | Risposta HTTP 429 — richiesta limitata dal rate limit. |
| `5` | **Non Trovato (Not Found)** | Risposta HTTP 404 — la risorsa richiesta non esiste. |

---

## 6. Esempi per Ambiente di Shell

### Bash / Zsh (Linux / macOS)
```bash
# Impostazione chiave di sessione
export OMI_API_KEY="omi_dev_your_actual_key_here"

# Esecuzione con controllo del codice di uscita
omi --json memory list --limit 10
if [ $? -ne 0 ]; then
    echo "Errore durante la consultazione delle memorie Omi" >&2
fi
```

### PowerShell (Windows)
```powershell
# Impostazione variabile d'ambiente in PowerShell
$env:OMI_API_KEY = "omi_dev_your_actual_key_here"

# Conversione dell'output JSON direttamente in oggetti PowerShell
$memories = omi --json memory list | ConvertFrom-Json
$memories | Select-Object id, content, category

# Controllo errori tramite $LASTEXITCODE
if ($LASTEXITCODE -ne 0) {
    Write-Error "Comando Omi fallito con codice $LASTEXITCODE"
}
```

---

## 7. Integrazione con l'API Desktop Locale

Quando l'applicazione Omi Desktop è in esecuzione sulla macchina, la CLI può interrogare la timeline locale senza effettuare richieste cloud:

```bash
# Configurazione dell'endpoint locale (usando variabili d'ambiente per proteggere il token)
export OMI_LOCAL_API_URL="http://127.0.0.1:47778"
read -r -s -p "Desktop token: " OMI_LOCAL_TOKEN; echo
export OMI_LOCAL_TOKEN

# Verifica dello stato di connessione locale
omi --json local status

# Ricerca nella timeline visiva recente
omi --json local search-screen "Rapporto trimestrale" --days 7 --app Safari
```

---

## 8. Gestione di Profili Multipli (Profiles)

Per passare da account personali a lavorativi o ambienti di test, utilizzare l'opzione `--profile`. Le impostazioni vengono conservate in `~/.omi/config.toml`:

```bash
# Creazione e autenticazione profilo personale
omi --profile personal auth login

# Creazione e autenticazione profilo di lavoro
omi --profile work auth login

# Esecuzione di comandi con un profilo specifico
omi --profile work memory list

# Configurazione profilo di test con endpoint personalizzato
omi --profile staging --api-base https://api-staging.omi.me memory list
```

---

## 9. Buone Pratiche di Sicurezza

* **Nessun token in Git:** Non salvare mai chiavi API in repository di versione pubblici.
* **Cronologia Terminale:** Evitare di passare segreti in chiaro come argomenti CLI; preferire l'immissione interattiva o `OMI_API_KEY`.
* **Permessi Cartella:** Su sistemi Unix limitare i permessi della cartella di configurazione `~/.omi/` (`chmod 700 ~/.omi`).
