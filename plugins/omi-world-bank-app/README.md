# World Bank Economic Indicators Integration for Omi

Provides real-time macroeconomic indicators, GDP, inflation, population, life expectancy, unemployment, and cross-country comparisons using the public World Bank Open Data API (no API keys required).

## Features

- **Economic Snapshot (`/tools/economic_snapshot`)**: Complete macroeconomic overview of a country (GDP, GDP Growth, Inflation %, Population, Unemployment %, Life Expectancy).
- **Indicator Time-Series History (`/tools/indicator_history`)**: Multi-year historical records for economic metrics.
- **Cross-Country Comparison (`/tools/compare_indicator`)**: Side-by-side metric comparison between two nations.
- **Zero API Keys**: Uses public open endpoints with no subscription requirements.
- **100% Hermetic Tests**: Fast unit test execution under standard library Python.

## Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/tools/economic_snapshot` | `POST` | Retrieve major macroeconomic indicators for a country. |
| `/tools/indicator_history` | `POST` | Get historical time-series for a specific indicator. |
| `/tools/compare_indicator` | `POST` | Compare an indicator between two countries. |
| `/` | `GET` | HTML documentation and app dashboard. |
| `/manifest.json` | `GET` | Omi integration plugin manifest. |
| `/health` | `GET` | Health check endpoint. |
| `/privacy` | `GET` | Privacy policy. |

## Running Locally

```bash
cd plugins/omi-world-bank-app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Running Tests

```bash
python3 plugins/omi-world-bank-app/test_main.py
```
