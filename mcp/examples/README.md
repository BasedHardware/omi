# MCP Omi Examples

This directory contains example applications for interacting with the **hosted
Omi MCP server** at `https://api.omi.me/v1/mcp` (Streamable HTTP) in different
frameworks. None of them require a local MCP process — authentication is a
Bearer MCP key in an `Authorization` header.

## Prerequisites

Before running the examples, make sure you have:

1. Python 3.11 or later installed
2. An OpenAI API key (`OPENAI_API_KEY`)
3. An Omi MCP API key (`OMI_MCP_API_KEY`, starts with `omi_mcp_`) — create one in
   the Omi app under **Settings → Developer Settings → MCP Server → API Keys**,
   or via **Use omi memory anywhere → Manual installation** in the macOS app

## Setup

1. Clone this repository
2. Create a virtual environment:
   ```
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file in this directory with the following values:
   ```
   OPENAI_API_KEY=your_openai_api_key
   OMI_MCP_API_KEY=omi_mcp_your_key_here
   ```

## Applications

### Main Streamlit App

The primary application is a Streamlit chat interface that lets you interact
with your Omi data through the hosted MCP server.

To run the Streamlit app:
```
streamlit run app.py
```

The app will open in your browser. Enter your `omi_mcp_...` key in the sidebar
settings before you start chatting (or export `OMI_MCP_API_KEY`).

### Example Scripts

This repository includes three example scripts demonstrating how to connect to
the hosted Omi MCP endpoint using different frameworks:

1. **DSPy Example** (dspy_ex.py) — `mcp.client.streamable_http` + `ClientSession`:
   ```
   python dspy_ex.py
   ```

2. **OpenAI Agents SDK Example** (openai_agents_sdk_ex.py) — `MCPServerStreamableHttp`:
   ```
   python openai_agents_sdk_ex.py
   ```

3. **LangChain Example** (langchain_ex.py) — `MultiServerMCPClient` with
   `streamable_http` transport + `create_react_agent`:
   ```
   python langchain_ex.py
   ```

Each example connects directly to `https://api.omi.me/v1/mcp` with your MCP key
and can be used as a reference for your own applications.

### Prefer a local stdio server?

The deprecated `mcp-server-omi` package can still be run locally for clients
that only support stdio. `uvx` ships with [uv](https://docs.astral.sh/uv/)
(`brew install uv`, or `pip install uv` — there is no separate `uvx` package).
See the package README for the hosted-first migration steps.

## Features

- Access and query your Omi data through natural language
- View memories and conversation history
- Interactive chat interface (Streamlit app)
- Example integrations with popular frameworks (DSPy, OpenAI Agents SDK, LangChain)

## Troubleshooting

- A `401` usually means the `OMI_MCP_API_KEY` value is missing, malformed, or a
  Developer API key (`omi_dev_...`) — MCP keys start with `omi_mcp_`
- Check that `OPENAI_API_KEY` is set for the model calls in the examples
- Ensure all dependencies are installed by running `pip install -r requirements.txt`
