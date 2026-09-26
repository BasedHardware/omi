# Omi World Universities & Colleges App

An integration app for [Omi](https://github.com/BasedHardware/omi) providing instant worldwide university discovery, official college websites, and higher education institution search powered by the public Hipo Universities API.

## Features

- **Search Universities**: Look up colleges and universities worldwide by name, keyword, or acronym with optional country filtering.
- **Universities by Country**: List top higher education institutions in any country.
- **Institutional Details**: Retrieve official domains, websites, and location metadata for any university.
- **Zero Configuration**: No API keys or authentication required.

## Endpoints

- `POST /tools/search_universities`: Search universities by query string and optional country.
- `POST /tools/universities_by_country`: List universities by country name.
- `POST /tools/university_details`: Retrieve institutional details and official links.
- `GET /manifest.json`: Omi plugin manifest.
- `GET /.well-known/ai-plugin.json`: OpenAI standard manifest.
- `GET /health`: Health status.
