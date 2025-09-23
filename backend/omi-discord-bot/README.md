# Omi Discord Bot

## How to run
    *   Python 3.14+
    *   `uv` package manager

**Installation**
    *   Clone the repository.
    *   Create a virtual environment: `uv venv env`
    *   Activate the virtual environment: `source env/bin/activate`
    *   Install dependencies: `uv pip install -r requirements.txt`

**Configuration**
    *   Create a `.env` file: `TOKEN=your_bot_token`

**Running the bot**
    *   Run the bot: `python main.py`

**Indexing the knowledge base**
    *   In your Discord server, run the `!index` command.

## Commands

*   `$index`: Indexes the `faq.json` file.
*   `$reload_index`: Reloads the BM25 index.
*   `$sync`: to sync slash command 
