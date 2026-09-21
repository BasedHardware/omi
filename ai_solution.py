```python
# The new Burmese (my) quickstart guide
---
title: "LLM/Agent Quickstart Guide"
description: "A quick start guide for LLM and Agent in the sdks/python-cli."
language: "my"
---

## LLM/Agent Quickstart Guide

### Getting Started

Let's explore how to use the Large Language Model (LLM) and the AI Agent in the `sdks/python-cli` package.

### What is LLM?

LLM stands for Large Language Model. It's a type of AI model that can understand and generate human-like text.

### What is an AI Agent?

An AI Agent is a system that uses LLMs to perform tasks, such as answering questions, providing explanations, and solving problems.

### Prerequisites

- Python 3.8 or higher is required.
- The `openai` package must be installed.

### Installation

Run the following command to install the package:

```bash
pip install openai
```

### Example

Here's a simple example of how to use the Agent:

```python
from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "What is the capital of Myanmar?"}]
)
print(response.choices[0].message.content)
```

### Conclusion

We've walked through the basics of using LLM and Agent in the `sdks/python-cli` package. Start using them in your projects!

---

# The updated README.md

```bash
--- 
title: "Examples"
description: "Examples of using sdks/python-cli."
---

## Examples

Here, you'll find various examples demonstrating the use of sdks/python-cli.

- [Python Quickstart Guide](agent_quickstart.md)
- [Python Quickstart Guide in Burmese](agent_quickstart.my.md)
```

```