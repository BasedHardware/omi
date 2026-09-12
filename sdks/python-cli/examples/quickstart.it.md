# Guida Rapida omi-cli (Italiano)

> Guida pratica per interagire con Omi dal terminale. Adatta sia per persone che per agenti AI.

`omi-cli` è l'interfaccia a riga di comando ufficiale per interagire con le API sviluppatore di [Omi](https://omi.me). Gestisce in modo efficiente e scriptabile le quattro risorse principali di Omi — **memorie, conversazioni, action item e obiettivi**.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentazione ufficiale:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Codice sorgente:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installazione

Il metodo consigliato è usare `pipx` per isolare le dipendenze.

```bash
# Consigliato: installa con pipx
pipx install omi-cli

# In alternativa: usa pip
pip install omi-cli
```

> **Importante: differenza tra nome del pacchetto e nome del comando**
> * Il pacchetto Python installato si chiama **`omi-cli`** (il pacchetto `omi` standalone è un altro pacchetto non correlato).
> * Il comando eseguibile nel terminale dopo l'installazione è **`omi`**.

Dopo l'installazione, verifica la versione e l'aiuto.

```bash
omi --version
omi --help
```

---

## 2. Autenticazione

`omi-cli` supporta due modalità di autenticazione.

| Modalità | Uso consigliato | Comando di esempio |
| :--- | :--- | :--- |
| **Chiave API sviluppatore (`omi_dev_*`)** | CI/CD, script automatici, agenti AI | `omi auth login --api-key ...` o variabile d'ambiente |
| **OAuth nel browser (Google/Apple)** | PC / laptop dello sviluppatore | `omi auth login --browser` |

### Login interattivo
Senza opzioni, ti verrà chiesto di scegliere tra login nel browser o inserimento della chiave API.

```bash
omi auth login
# 1) Browser — accedi con il tuo account Google o Apple (per persone)
# 2) API key — incolla la chiave sviluppatore da app.omi.me (per agenti/CI)
```

### Login diretto via browser
```bash
omi auth login --browser
```

### Uso della chiave API
Ottieni la chiave sviluppatore da **Developer → API Keys** su [app.omi.me](https://app.omi.me), poi impostala.

```bash
# Imposta tramite comando
omi auth login --api-key omi_dev_...

# Oppure tramite variabile d'ambiente (ideale per CI/CD o container)
export OMI_API_KEY=omi_dev_...
```

### Verifica dello stato di autenticazione
* `omi auth status`: mostra il profilo locale, il token mascherato e la data di scadenza (funziona offline).
* `omi auth whoami`: invia una richiesta reale al server Omi (richiede connessione di rete).

```bash
omi auth status
omi auth whoami
```

Per disconnettersi:
```bash
omi auth logout
```

---

## 3. Utilizzo Base

Puoi elencare e gestire le quattro risorse principali di Omi.

### Memorie (Memories)
Gestisce i fatti e le conoscenze apprese dal sistema.

```bash
# Elenca tutte le memorie
omi memory list

# Crea una nuova memoria
omi memory create "L'utente preferisce la modalità scura" --category lifestyle

# Visualizza i dettagli di una memoria specifica
omi memory get <MEMORY_ID>
```

### Conversazioni (Conversations)
Cronologia audio o testo delle conversazioni acquisite dal dispositivo indossabile o dall'app.

```bash
# Recupera le ultime 5 conversazioni
omi conversation list --limit 5

# Visualizza i dettagli della conversazione e la trascrizione
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Action Item
Attività o elementi di follow-up estratti automaticamente dalle conversazioni.

```bash
# Elenca solo gli action item ancora aperti
omi action-item list --open

# Segna un action item come completato
omi action-item complete <ACTION_ITEM_ID>
```

### Obiettivi (Goals)
Gestisce gli obiettivi di cui viene tracciato l'avanzamento.

```bash
# Elenca tutti gli obiettivi
omi goal list
```

---

## 4. Elaborazione Script e Output JSON (`--json`)

`omi-cli` supporta nativamente l'output JSON. Quando lo combini con `jq` o script Python, l'**opzione globale** `--json` deve essere posizionata prima del sottocomando.

```bash
# Ottieni l'elenco delle memorie in JSON ed estrai ID e contenuto
omi --json memory list | jq '.[] | {id, content, category}'

# Ottieni i titoli delle ultime 5 conversazioni
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# Elenca gli action item aperti
omi --json action-item list --open | jq '.[] | {id, description, due_at}'

# Elenca gli obiettivi
omi --json goal list | jq '.[] | {id, title, current: .current_value, target: .target_value}'
```

---

## 5. Diagnostica della Sessione

Usa questi comandi in coppia per risolvere rapidamente i problemi.

```bash
# 1) Controlla prima la configurazione locale
omi auth status

# 2) Verifica con il server Omi
omi auth whoami

# 3) Se necessario, riavvia il login
omi auth login
```

---

## 6. Migliori Pratiche

* **Usa `--json` negli script:** Evita il parsing di testo libero; affidati sempre all'output JSON strutturato.
* **Isola gli ambienti con `pipx`:** Evita conflitti di dipendenze con altri pacchetti Python.
* **Non condividere le chiavi API:** Le chiavi `omi_dev_*` concedono accesso completo all'account — conservale in un gestore di segreti o in variabili d'ambiente.
* **Disconnettiti dai dispositivi condivisi:** Usa `omi auth logout` dopo le sessioni su macchine condivise.

---

## 7. Risoluzione dei Problemi

| Sintomo | Causa probabile | Soluzione |
| :--- | :--- | :--- |
| `command not found: omi` | Il PATH non contiene la directory bin di pipx | Esegui `pipx ensurepath` e riavvia il terminale |
| `401 Unauthorized` | Chiave API non valida o scaduta | Genera una nuova chiave su app.omi.me e aggiorna |
| `connection refused` | Nessun accesso di rete al server Omi | Verifica la connessione internet e le impostazioni proxy |
| `permission denied` sui file di configurazione | La directory di configurazione non è scrivibile | Controlla i permessi di `~/.omi/config.toml` |

---

## 8. Link Rapidi

* Repository sorgente: [github.com/BasedHardware/omi](https://github.com/BasedHardware/omi)
* Documentazione completa: [docs.omi.me](https://docs.omi.me)
* Issues e supporto: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
* Community Discord: invito disponibile tramite la home page di Omi