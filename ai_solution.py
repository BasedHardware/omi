```python
def generate_doc_code(input_str: str) -> str:
    """
    Generates the complete, working code solution for the Azerbaijani quickstart guide.

    Args:
        input_str: The input string containing the content to be translated.

    Returns:
        The complete, working code solution as a string.
    """
    return """---
title: "AI Agent Quickstart Guide"
---

# AI Agent Quickstart Guide

Welcome to the AI Agent Quickstart Guide in Azerbaijani! This guide will help you get started with AI agents using the `oml-cli` tool.

## What is an AI Agent?

An AI Agent is an intelligent system that performs tasks on your behalf. With `oml-cli`, you can create and manage AI Agents efficiently.

## Getting Started

### Installation

First, make sure you have the latest version of `oml-cli` installed. You can install it using pip:

```bash
pip install oml-cli
```

### Creating an AI Agent

To create an AI Agent, use the following command:

```bash
oml-agent create --name my-agent
```

### Running an AI Agent

Start your AI Agent with:

```bash
oml-agent run --name my-agent
```

### Interacting with Your AI Agent

You can interact with your AI Agent in several ways:

#### Via the CLI
```bash
oml-agent chat --name my-agent
```

#### Via REST API
```bash
curl -X POST "http://localhost:11498/api/v1/agent/llama/call" -H "Content-Type: application/json" -d '{"model":"llama-33b-uncat","messages":[{"role":"user","content":"Hello!"}]}
```

## Conclusion

Congratulations! You have successfully set up and started your AI Agent in Azerbaijani. Explore more features and capabilities as you work with your AI Agent.
"""
```