# REST Countries & World Info Integration for Omi

Provides real-time country profiles, demographics, capitals, currencies, official languages, timezones, and borders to Omi chat tools through the public REST Countries API (no API keys required).

## Features

- **Country Overview (`/tools/country_overview`)**: Full demographic and geographic overview by country name or ISO 2/3 code (e.g. `Japan`, `France`, `DE`, `BRA`).
- **Capital Lookup (`/tools/search_by_capital`)**: Identify countries corresponding to a capital city name (e.g. `Tokyo`, `Canberra`).
- **Currency Search (`/tools/search_by_currency`)**: List all countries using a currency code or currency name (e.g. `EUR`, `USD`, `Yen`).
- **Language Search (`/tools/search_by_language`)**: List all countries where a specified language is officially spoken.
- **Zero API Keys**: Uses public open endpoints with no subscription requirements.
- **100% Hermetic Tests**: Instant unit test execution under standard library Python.

## Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/tools/country_overview` | `POST` | Retrieve detailed country profile (capital, population, currencies, borders, timezones, map link). |
| `/tools/search_by_capital` | `POST` | Find country profile by capital city. |
| `/tools/search_by_currency` | `POST` | Search countries by currency name or code. |
| `/tools/search_by_language` | `POST` | Search countries by official language name. |
| `/` | `GET` | HTML documentation and app dashboard. |
| `/manifest.json` | `GET` | Omi integration plugin manifest. |
| `/health` | `GET` | Health check endpoint. |
| `/privacy` | `GET` | Privacy policy. |

## Running Locally

```bash
cd plugins/omi-countries-info-app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Running Tests

```bash
python3 plugins/omi-countries-info-app/test_main.py
```
