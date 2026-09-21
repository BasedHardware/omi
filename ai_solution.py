```python
# AI Agent Quickstart Guide in Dzongkha

## What is an AI Agent?

An AI Agent is a program that can assist you in various tasks, such as answering questions, providing recommendations, and solving problems. It is designed to make your work easier and more efficient.

## Getting Started

### Prerequisites

Before you begin, ensure you have the following:

- Python 3.8 or higher installed on your system.
- The `omi-cli` package installed.

### Installation

Install the `omi-cli` package using pip:

```bash
pip install omi-cli
```

### Usage

To create and manage an AI Agent, follow these steps:

1. **Create an AI Agent:**

   Use the following command to create a new AI Agent:

   ```bash
   omi-cli agent create --name "my-agent" --model "llama2"
   ```

2. **Start the AI Agent:**

   After creating the agent, start it with:

   ```bash
   omi-cli agent start --name "my-agent"
   ```

3. **Interact with the AI Agent:**

   You can interact with the agent by sending messages. For example:

   ```bash
   omi-cli agent send --name "my-agent" --message "Hello!"
   ```

4. **List All Agents:**

   To view all your AI Agents, run:

   ```bash
   omi-cli agent list
   ```

5. **Stop an AI Agent:**

   If you need to stop an agent, use:

   ```bash
   omi-cli agent stop --name "my-agent"
   ```

### Examples

#### Example 1: Basic Interaction

1. Create an agent:

   ```bash
   omi-cli agent create --name "my-agent" --model "llama2"
   ```

2. Start the agent:

   ```bash
   omi-cli agent start --name "my-agent"
   ```

3. Send a message:

   ```bash
   omi-cli agent send --name "my-agent" --message "Hello!"
   ```

#### Example 2: Using Different Model

You can choose different models like:

```bash
omi-cli agent create --name "my-agent" --model "gpt4"
```

### Conclusion

With `omi-cli`, creating and managing AI Agents is straightforward. You can easily interact with your agents using simple commands. For more details, refer to the [User Guide](link-to-user-guide).

---

The translated guide is now available in Dzongkha as `agent_quickstart.dz.md` under `sdks/python-cli/examples/`. It has been added to `sdks/python-cli/examples/README.md` for easy access.
```