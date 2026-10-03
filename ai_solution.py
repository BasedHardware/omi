```markdown
# Schnellstartanleitung für LLM/Agent in luxemburgischer Sprache

Willkommen bei der Schnellstartanleitung für LLM/Agent in luxemburgischer Sprache!

## Grundlagen

Das `omi-cli` ist eine mächtige Befehlszeilengrundlage für die Integration von LLMs und Agenten. Sie können es verwenden, um die Leistung von LLMs (wie GPT) und intelligenten Agenten zu steuern.

## Installation

Führen Sie den folgenden Befehl aus, um `omi-cli` zu installieren:

```bash
pip install omi-cli
```

## Erste Schritte

### 1. Öffnen Sie die Liste der verfügbaren Modelle

```bash
$ omi list models
```

### 2. Wählen Sie ein Modell aus

```bash
$ omi config model-name gpt-4
```

### 3. Fragen Sie das Modell

```bash
$ omi chat "Hallo, wie geht's?"
```

## Agenten

### 1. Öffnen Sie die Liste der verfügbaren Agenten

```bash
$ omi list agents
```

### 2. Wählen Sie einen Agenten aus

```bash
$ omi config agent-name zero-shot-co
```

### 3. Konfigurieren Sie den Agenten

```bash
$ omi config agent-prompt "Seien Sie ein Experte für [Bereich]."
```

### 4. Fragen Sie den Agenten

```bash
$ omi agent "Was ist der Unterschied zwischen Chat und Agent?"
```

## Hilfe

Falls Sie Hilfe benötigen, verwenden Sie:

```bash
$ omi --help
```

oder

```bash
$ omi help
```

## Weitere Informationen

Machen Sie auf [GitHub](https://github.com/your-repository) Bekanntschaft mit unseren anderen Beispielen und Dokumentationen.

---

### Credits

Vielen Dank für die Verwendung von `omi-cli`!
```

---

```markdown
# sdks/python-cli/examples/README.md

```

```markdown
## Beispiele

Die Beispiele sind in verschiedenen Sprachen verfügbar:

- [agent_quickstart.md](agent_quickstart.md): Schnellstartanleitung für LLM/Agent
- [agent_quickstart.lb.md](agent_quickstart.lb.md): Schnellstartanleitung für LLM/Agent in Luxemburgischer Sprache
```

```