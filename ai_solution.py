```markdown
# Quickstart Guide per gli agenti (Claude Code, Cursor, bot custom)

Questo è un'introduzione rapida per avviare l'uso degli agenti con la CLI di Python.

## 1. Introduzione agli agenti
Agenti sono modelli di linguaggio per rispondere in modo contestuato.

## 2. Configurare l'ambiente
### 2.1. Installare Python
```bash
python --version
```
### 2.2. Installare la CLI
```bash
pip install "python-omni"
```

## 3. Comandi di base
### 3.1. Verificare la versione
```bash
python -m omni --version
```

## 4. Utilizzo di base
### 4.1. Interagire con un agente
```bash
python -m omni agent --model Claude Code --prompt "Ciao!"
```

## 5. Modelli supportati
- Claude Code
- Cursor
- Custom bots

## 6. Opzioni di comando
### 6.1. Opzioni di base
```bash
--api-key "<OMI_API_KEY>"  # Chiave di API
--local-api-url "<OMI_LOCAL_API_URL>"  # URL locale
--local-token "<OMI_LOCAL_TOKEN>"  # Token locale
```

## 7. Variabili di ambiente
```bash
export OMI_API_KEY="your_api_key"
export OMI_LOCAL_API_URL="http://localhost:11439"
export OMI_LOCAL_TOKEN="your_token"
```

## 8. Limiti di frequenza
```bash
# Codici di uscita:
0: Success
1: Errore generico
2: Timeout
3: Parametri non validi
4: Risposta vuota
5: Risposta troppo grande
```

## 9. Esempi di codici
### 9.1. Esempio base
```python
from omni import agent
response = agent(
    model="Claude Code",
    prompt="Ciao!"
)
print(response)
```

## 10. Documentazione
Ulteriori dettagli sono disponibili all'indirizzo:
https://github.com/BasedHardware/omi

## 11. Conclusione
Grazie per aver scelto la CLI di Python.
```

Questo codice rappresenta la guida italiana aggiunta nella cartella examples, mantenendo lo stesso struttura e contenuti del file originale in inglese, con traduzione accurate e idomatica.