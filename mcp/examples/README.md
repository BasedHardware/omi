# MCP Omi Examples

This repository contains example applications for interacting with the Omi API using MCP (Model Controlled Programs) in different frameworks.

## Prerequisites

Before running the examples, make sure you have:

1. Python 3.8 or later installed
2. `uvx` command-line tool installed (`pip install uvx`)
3. An OpenAI API key
4. An Omi UID (Unique Identifier)

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
4. Create a `.env` file in the root directory with the following values:
   ```
   OPENAI_API_KEY=your_openai_api_key
   OMI_UID=your_omi_uid
   ```

## Applications

### Main Streamlit App

The primary application is a Streamlit chat interface that allows you to interact with your Omi data.

To run the Streamlit app:
```
streamlit run app.py
```

The app will open in your browser. You'll need to enter your Omi UID in the sidebar settings before you can start chatting.

### Example Scripts

This repository includes three example scripts demonstrating how to interact with Omi data using different frameworks:

1. **DSPy Example** (dspy_ex.py):
   ```
   python dspy_ex.py
   ```

2. **OpenAI Agents SDK Example** (openai_agents_sdk_ex.py):
   ```
   python openai_agents_sdk_ex.py
   ```

3. **LangChain Example** (langchain_ex.py):
   ```
   python langchain_ex.py
   ```

Each example shows a different method of connecting to the Omi API using MCP and can be used as a reference for your own applications.

## Features

- Access and query your Omi data through natural language
- View memories and conversation history 
- Interactive chat interface (Streamlit app)
- Example integrations with popular frameworks (DSPy, OpenAI Agents SDK, LangChain)

## Troubleshooting

- If you encounter errors about missing `uvx`, make sure it's installed and in your PATH
- Check that both environment variables (OPENAI_API_KEY and OMI_UID) are set correctly
- Ensure all dependencies are installed by running `pip install -r requirements.txt`

```
OPENAI_API_KEY=
OMI_UID=
```