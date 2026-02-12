# Plugins Example Project

This project is a FastAPI application.

## Prerequisites

- Python 3.7+
- .env file with necessary environment variables

## Installation

1. Clone the repository:
   `git clone `
2. Navigate to the project directory:
   `cd plugins/example`
3. Install the required packages:
   pip install -r requirements.txt
4. Create a `.env` file in the project root with the following environment variables:

```dotenv
OPENAI_API_KEY=
REDIS_DB_HOST=
REDIS_DB_PORT=
REDIS_DB_PASSWORD=
ASKNEWS_CLIENT_ID=
ASKNEWS_CLIENT_SECRET=
GROQ_API_KEY=
MULTION_API_KEY=
MEM0_API_KEY=
```

Fill in the values for each variable as needed.

## Running the Project

1. Ensure you have filled in the `.env` file with the necessary environment variables.
2. Install the requirements.txt by running:
   `pip install -r requirements.txt`

3. Run the project: `fastapi run` or `fastapi dev` This will start the FastAPI application.

## Project Structure

- `main.py`: The main FastAPI application file
- `templates/`: Directory containing HTML templates
- `_mem0.py` and `_multion.py`: Routers for additional functionalities
- `db.py`: Database operations
- `llm.py`: Contains the news checker functionality
- `models.py`: Data models
- `notion_utils.py`: Utilities for Notion integration

## Features

- Notion CRM integration
- News checking functionality
- Memory storage
- External integrations (Mem0 and Multion)

## API Endpoints

- `/setup-notion-crm`: Set up Notion CRM
- `/creds/notion-crm`: Store Notion CRM credentials
- `/setup/notion-crm`: Check if Notion CRM setup is completed
- `/notion-crm`: Store memory in Notion database
- `/news-checker`: Check news based on conversation transcript

For more details on how to use these endpoints, refer to the code documentation or contact the project maintainer.
