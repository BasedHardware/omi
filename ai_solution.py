```markdown
---
title: "Quickstart: Create an AI agent with the Irish (ga) interface"
description: "A quickstart guide for creating an AI agent using the Irish (ga) interface with omi-cli."
---

# Quickstart: Create an AI agent with the Irish (ga) interface

Welcome to the quickstart guide for creating an AI agent with the Irish (ga) interface using `omi-cli`. This guide will help you get started with the AI agent in Irish.

## Prerequisites

Before you begin, ensure you have:

- The `omi-cli` installed and configured.
- Your API key set as `OMI_API_KEY` or through the `.env` file.

## Step 1: Create a new AI agent

Run the following command to create a new AI agent in Irish:

```bash
omi-cli agent new --lang ga
```

## Step 2: Start the AI agent

Start the agent with:

```bash
cd my-agent
pip install -r requirements.txt
python -m agent
```

## Step 3: Interact with the AI

You can now interact with the AI in Irish. Type your questions or commands in Irish, and the AI will respond in Irish.

## Step 4: Customize the agent (Optional)

You can customize the agent's responses by editing the `config.yml` file:

```yaml
name: Your Agent's Name
description: Your Agent's Description
```

## Step 5: Headless mode

For headless operation, use:

```bash
OMI_API_KEY=your_api_key omi-cli agent run --headless
```

## Step 6: Verify output

The agent will respond in Irish, ensuring parity with the English version.

## Conclusion

You've successfully created and started an AI agent in Irish using `omi-cli`. The agent is now ready to assist you in Irish.

---

```