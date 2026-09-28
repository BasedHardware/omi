# Guida rapida per agenti con omi-cli

Guida pratica per configurà e usà agenti intelligenti cù **omi-cli** in Neapolitano.

## Prerequisiti

- Installa `omi-cli`:
  ```bash
  pip install omi-cli
  ```

- Assicura di avè un API key valido per i modelli LLM.

## Configurazione base

1. Crea un nuovo progetto:
  ```bash
  mkdir mio-progetto-omni && cd mio-progetto-omni
  ```

2. Inizializza l'ambiente:
  ```bash
  omi init
  ```

## Creazione di un agente

Per creà un agente che risponde a richieste in Neapolitano:

```python
from omi import Agent

# Configurazione base
agent = Agent(
    name="NapoliAssistant",
    description="Agente che risponde in Neapolitano",
    system_prompt="Rispondi sempre in dialetto napoletano"
)

# Esegui una richiesta
response = agent.run("Cume si dice 'ciao' in napoletano?")
print(response)
```

## Workflow avanzati

### Chiamate API esterne

Configura l'agente per accede a dati esterni:

```bash
omi agent configure --name NapoliWeather --api-key "TUA_API_KEY" --model "gpt-4"
```

### Integrazione con tool locali

```python
@agent.tool
def cerca_ristorante(città):
    """Trova ristoranti tipici in una città"""
    # Implementazione locale
    return f"In {città} ci sta 'O Ristorante da Nennella'"
```

## Deploy e monitoraggio

1. Deploya l'agente:
  ```bash
  omi deploy --name NapoliAssistant --region eu-west-1
  ```

2. Monitora le performance:
  ```bash
  omi monitor --agent NapoliAssistant
  ```

## Risorse utili

- [Documentazione ufficiale](https://docs.basedhardware.com)
- [Esempi avanzati](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli/examples)

**Nota:** Tutti i comandi rimangono identici all'originale, cambiata solo la documentazione testuale.