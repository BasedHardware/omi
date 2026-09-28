# Agent Quickstart Guide (Silesian)

Początek z agentami w OMI CLI.

## Instalacija

Przed rozpoczęciem, upewnij się, że masz zainstalowaną najnowszą wersję `omi-cli`:

```bash
pip install --upgrade omi-cli
```

## Tworzenie prostego agenta

Stwórz nowy plik `agent.py` z następującą zawartością:

```python
from omi import Agent

class MyAgent(Agent):
    async def run(self):
        print("Agent działa!")
        return {"status": "success"}

agent = MyAgent()
agent.run()
```

## Uruchamianie agenta

Uruchom agenta za pomocą CLI:

```bash
omi agent run agent.py
```

## Zaawansowane funkcje

### Konfiguracja środowiska

Możesz skonfigurować środowisko agenta poprzez plik `.env`:

```env
OMI_AGENT_MODEL=gpt-4
OMI_AGENT_TEMPERATURE=0.7
```

### Obsługa błędów

Agent automatycznie loguje błędy do `logs/agent_errors.log`. Możesz je przeglądać:

```bash
omi logs tail agent_errors.log
```

## Przykładowe scenariusze

### Scenariusz 1: Automatyzacja zadań

```python
class TaskAutomationAgent(Agent):
    async def run(self):
        tasks = ["task1", "task2", "task3"]
        for task in tasks:
            print(f"Wykonuję zadanie: {task}")
            await self.sleep(1)
        return {"completed": tasks}
```

### Scenariusz 2: Przetwarzanie danych

```python
class DataProcessorAgent(Agent):
    async def run(self):
        data = await self.fetch_data("https://api.example.com/data")
        processed = [x * 2 for x in data]
        return {"processed": processed}
```
