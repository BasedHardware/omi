# omi-cli — guida rapida in italiano

> Guida pratica per lavorare con Omi dal terminale. Adatta sia alle persone sia agli agenti IA.

`omi-cli` è il client ufficiale a riga di comando per l'API per sviluppatori di [Omi](https://omi.me).
Offre un accesso rapido e adatto agli script alle quattro entità principali di Omi:
ricordi, conversazioni, attività e obiettivi.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Documentazione:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Codice sorgente:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Installazione

Il metodo consigliato è `pipx`: installa lo strumento in un ambiente isolato,
così le sue dipendenze non entrano in conflitto con i vostri progetti.

```bash
# consigliato: installazione tramite pipx
pipx install omi-cli

# oppure tramite pip
pip install omi-cli
```

> **Importante: il nome del pacchetto e il nome del comando sono diversi.**
> * Il pacchetto installato è **`omi-cli`** (il pacchetto separato `omi` è un altro progetto, non correlato).
> * Dopo l'installazione si esegue il comando **`omi`**.

Verificate che tutto funzioni:

```bash
omi --version
omi --help
```

---

## 2. Autenticazione

`omi-cli` supporta due modi di accedere.

| Metodo | Adatto a | Comando |
| :--- | :--- | :--- |
| **Chiave sviluppatore (`omi_dev_*`)** | CI/CD, script, agenti IA | `omi auth login --api-key ...` oppure variabile d'ambiente |
| **Accesso via browser (Google/Apple)** | Lavoro sul proprio computer | `omi auth login --browser` |

### Accesso interattivo

Senza opzioni, il comando chiede quale metodo si vuole usare:

```bash
omi auth login
# 1) Browser — accedi con Google o Apple (comodo per le persone)
# 2) API key — incolla la chiave sviluppatore da app.omi.me (comodo per agenti e CI)
```

Se si sceglie la chiave, l'input è mascherato, così la chiave non resta nella cronologia del terminale.

### Direttamente dal browser

```bash
omi auth login --browser
```

### Tramite chiave sviluppatore

La chiave si ottiene su [app.omi.me](https://app.omi.me) sotto **Developer → API Keys**.

```bash
# salvare la chiave nella configurazione
omi auth login --api-key omi_dev_...

# oppure passarla tramite l'ambiente — preferito per CI/CD e container
export OMI_API_KEY=omi_dev_...
```

La variabile d'ambiente `OMI_API_KEY` viene usata quando nel profilo attivo non è salvata
alcuna chiave; in un container non serve quindi scrivere nulla su disco. Se il profilo
ha già una chiave, questa ha la precedenza sulla variabile d'ambiente.

### Verificare l'accesso

Due comandi rispondono a domande diverse e non vanno confusi:

* `omi auth status` — ciò che è salvato **in locale**: profilo, chiave mascherata, data di scadenza.
  Funziona senza rete.
* `omi auth whoami` — richiesta **al server Omi**: verifica che la chiave sia davvero
  accettata. Richiede la rete.

```bash
omi auth status    # controllo locale, offline
omi auth whoami    # controllo sul server
```

Rinnovare un token in scadenza senza accedere di nuovo — questo comando vale **solo per
le sessioni browser/OAuth**. Per un profilo autenticato con chiave API (`omi_dev_*`),
`omi auth refresh` fallisce con un errore d'uso (codice 1): non c'è alcun token da rinnovare —
ruotate la chiave nell'app web di Omi se necessario:

```bash
omi auth refresh
```

Disconnettersi:

```bash
omi auth logout
```

---

## 3. Comandi di base

### Ricordi (memories)

Fatti e conoscenze che il sistema ha memorizzato su di voi.

```bash
# elenco dei ricordi
omi memory list

# crearne uno nuovo
omi memory create "L'utente preferisce il tema scuro" --category lifestyle

# vederne uno in particolare
omi memory get <MEMORY_ID>
```

### Conversazioni (conversations)

Cronologia vocale e testuale dal dispositivo o dall'app.

```bash
# le 5 conversazioni più recenti
omi conversation list --limit 5

# una conversazione completa con trascrizione
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Attività (action items)

Attività che Omi ha dedotto dalle conversazioni.

```bash
# solo quelle aperte
omi action-item list --open

# segnare come completata
omi action-item complete <ACTION_ITEM_ID>
```

### Obiettivi (goals)

```bash
# elenco degli obiettivi
omi goal list

# registrare un nuovo valore di avanzamento (richiede ENTRAMBI gli argomenti: obiettivo e valore)
omi goal progress <GOAL_ID> 25

# cronologia delle modifiche
omi goal history <GOAL_ID>
```

---

## Fare domande con parole proprie (`ask`)

Un comando di primo livello separato: pone una domanda in linguaggio naturale,
e la risposta viene costruita a partire dalle vostre conversazioni.

```bash
omi ask "cosa ho deciso riguardo al trasloco"
omi --json ask "quali attività ho promesso di chiudere questa settimana"
```

---

## 4. JSON e script (`--json`)

`omi-cli` può produrre JSON leggibile dalla macchina. L'opzione `--json` è **globale**
e va quindi posizionata **prima** del sottocomando.

```bash
# ricordi: estrarre id, testo e categoria
omi --json memory list | jq '.[] | {id, content, category}'

# titoli delle conversazioni recenti
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# attività aperte
omi --json action-item list --open | jq '.'
```

> **Errore frequente.** `--json` viene prima del sottocomando, non dopo.
> * Corretto: `omi --json memory list`
> * Sbagliato: `omi memory list --json`

In modalità `--json` su stdout non viene scritto altro che il JSON stesso —
gli script possono farvi affidamento.

---

## 5. Codici di uscita

I codici sono stabili, così la logica di script e CI può diramare su di essi.

| Codice | Significato | Quando |
| :---: | :--- | :--- |
| `0` | Successo | Il comando è stato eseguito |
| `1` | Errore di chiamata | Validazione interna di omi-cli (es. `--browser` e `--api-key` insieme, scelta di accesso non valida, stdin vuoto) |
| `2` | Errore di accesso | Non autenticati, chiave non valida o scaduta |
| `3` | Errore del server | Risposta 5xx, timeout, nessuna connessione |
| `4` | Troppe richieste | 429 Too Many Requests |
| `5` | Non trovato | 404, l'id non esiste |

> **Nota.** Opzioni sconosciute e argomenti mancanti vengono intercettati da Click e restituiscono il codice `2`.

Esempio di controllo in Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "la chiave funziona"
else
  code=$?
  [ "$code" -eq 2 ] && echo "accedere di nuovo"
  [ "$code" -eq 3 ] && echo "il server è giù, riprovare più tardi"
fi
```

---

## 6. Variabili d'ambiente

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_la_vostra_chiave"

omi --json memory list --limit 10
```

Perché la chiave venga caricata nelle nuove sessioni, aggiungete la riga a `~/.bashrc` o `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_la_vostra_chiave"

# parsing JSON con PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Per una configurazione permanente:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_la_vostra_chiave", "User")
```

---

## 7. L'app Omi Desktop in locale

Se l'app desktop Omi è in esecuzione, una parte dei dati è disponibile
direttamente, senza passare dal cloud.

```bash
# indicare l'indirizzo dell'API locale
omi local configure --url http://127.0.0.1:47778 --token IL_VOSTRO_TOKEN

# verificare che risponda
omi --json local status

# ricerca nella cronologia dello schermo
omi --json local search-screen "prezzi" --days 7 --app Safari

# screenshot per id
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# SQL arbitrario sul database locale
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Flusso consigliato: prima `local status`, poi `local tools` — per vedere gli strumenti
disponibili e i loro parametri — e solo dopo le chiamate.

---

## 8. Profili

Se avete più account o ambienti, separateli con i profili.
Le impostazioni sono salvate in `~/.omi/config.toml`.

```bash
# accesso al profilo personale
omi --profile personal auth login

# accesso al profilo di lavoro
omi --profile work auth login

# eseguire un comando in un profilo specifico
omi --profile work memory list
```

Il profilo utilizzato è determinato in quest'ordine: l'opzione `--profile` (o `-p`)
ha la precedenza su tutto il resto; poi la variabile d'ambiente `OMI_PROFILE`;
poi il profilo attivo definito in `~/.omi/config.toml`; e infine, come fallback,
il profilo `default`.

Vedere e modificare la configurazione stessa:

```bash
# cosa è configurato ora
omi config show

# dove si trova il file di configurazione
omi config path

# modificare un valore
omi config set api_base https://api.omi.me
```

---

## 9. Prossimi passi

* [`agent_quickstart.md`](./agent_quickstart.md) — come collegare `omi-cli` a un agente IA.
* [`shell_examples.sh`](./shell_examples.sh) — esempi pronti per la shell.
* [Documentazione di Omi](https://docs.omi.me/doc/developer/cli/introduction) — il riferimento completo dei comandi.
