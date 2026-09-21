```python
## Quickstart Guide for LLM/Agent Workflows with `dogri-cli`

### Overview
This guide provides a concise introduction to using the Dogri (`doi`) LLM and Agent features with the `dogri-cli` command-line interface.

### Prerequisites
- Ensure you have `dogri-cli` installed.
- Copy the `dogri-cli` command to your environment.

### Basic Usage
1. **List Available Models**
   ```bash
   dogri-cli --list
   ```

2. **Use the LLM with Default Settings**
   ```bash
   dogri-cli --model "gpt-4"
   ```

3. **Execute Agent Command**
   ```bash
   dogri-cli --agent "write a poem about the Dogri language"
   ```

4. **View Available Commands**
   ```bash
   dogri-cli --help
   ```

### Advanced Usage
- **Set API Key**
  ```bash
  dogri-cli --api-key "your-api-key"
  ```

- **List Available Models**
  ```bash
  dogri-cli --list
  ```

- **Custom Model Selection**
  ```bash
  dogri-cli --model "gpt-4" --prompt "Explain quantum computing in simple terms."
  ```

### Conclusion
This quickstart guide offers a concise introduction to using Dogri (`doi`) with `dogri-cli`, covering basic and advanced use cases.

---

### [agent_quickstart.doi.md](sdks/python-cli/examples/agent_quickstart.doi.md)
```
---
title: "LLM/Agent Quickstart Guide (Dogri)"
description: "A concise introduction to using Dogri (`doi`) with `dogri-cli`."
---
```

```