```markdown
---
title: German (de) Agent Quickstart Guide
description: German technical translation of the agent-focused CLI quickstart guide for LLM harnesses.
---

# German (de) Agent Quickstart Guide

Willkommen bei der Schnellstartanleitung für den deutschen (de) Agent.

## Grundlagen

### Was ist der Agent?
Der Agent ist ein LLM-Harnes (Large Language Model) mit deutscher Sprachunterstützung.

### Unterstützte Sprachen
- **Sprachen:** Deutsch (de), Englisch (en), und weitere.
- **Standard:** Deutsch (de).

### Parameter

#### Befehlszeilenflagge
- **`--language=de`**
- **`--model=gpt-4**

### Umgebungsvariablen
- **`LANGUAGE=de`**
- **`MODEL=gpt-4`

## Installation

### Herunterladen
```bash
pip install "llm-harness[agents]"
```

### Konfiguration
```bash
export AGENT_MODEL=gpt-4
export AGENT_LANGUAGE=de
```

## Erste Schritte

### Beispiel
```bash
llm-harness --agent --language=de --model=gpt-4
```

### Erklärung
- **`--agent`**: Aktiviert den Agent.
- **`--language=de`**: Setzt die Sprache auf Deutsch.
- **`--model=gpt-4`**: Wählt das Modell.

## Weitere Beispiele

### Mit Umgebungsvariablen
```bash
export AGENT_MODEL=gpt-4
export AGENT_LANGUAGE=de
llm-harness --agent
```

### Ohne Parameter
```bash
llm-harness --agent
```

## Hilfe

### Parameterliste
```bash
llm-harness --agent --help
```

### Beispiel
```bash
llm-harness --agent --language=de --model=gpt-4
```

## Fehlerbehandlung

### Unklarheiten
```bash
llm-harness --agent --language=de --model=gpt-4
```

## Fertig
```

---

# Fügt die Datei an README.md hinzu
```markdown
# German (de) Agent Quickstart Guide

Willkommen bei der Schnellstartanleitung für den deutschen (de) Agent.

## Grundlagen

### Was ist der Agent?
Der Agent ist ein LLM-Harnes (Large Language Model) mit deutscher Sprachunterstützung.

### Unterstützte Sprachen
- **Sprachen:** Deutsch (de), Englisch (en), und weitere.
- **Standard:** Deutsch (de).

### Parameter

#### Befehlszeilenflagge
- **`--language=de`**
- **`--model=gpt-4`

### Umgebungsvariablen
- **`LANGUAGE=de`**
- **`MODEL=gpt-4`

## Installation

### Herunterladen
```bash
pip install "llm-harness[agents]"
```

### Konfiguration
```bash
export AGENT_MODEL=gpt-4
export AGENT_LANGUAGE=de
```

## Erste Schritte

### Beispiel
```bash
llm-harness --agent --language=de --model=gpt-4
```

### Erklärung
- **`--agent`**: Aktiviert den Agent.
- **`--language=de`**: Setzt die Sprache auf Deutsch.
- **`--model=gpt-4`**: Wählt das Modell.

## Weitere Beispiele

### Mit Umgebungsvariablen
```bash
export AGENT_MODEL=gpt-4
export AGENT_LANGUAGE=de
llm-harness --agent
```

### Ohne Parameter
```bash
llm-harness --agent
```

## Hilfe

### Parameterliste
```bash
llm-harness --agent --help
```

### Beispiel
```bash
llm-harness --agent --language=de --model=gpt-4
```

## Fehlerbehandlung

### Unklarheiten
```bash
llm-harness --agent --language=de --model=gpt-4
```

## Fertig
```