# Omi Craft Brewery Finder App

An integration app for [Omi](https://github.com/BasedHardware/omi) providing craft brewery, taproom, brewpub, and cidery discovery powered by the public Open Brewery DB API.

## Features

- **Search Breweries**: Search craft breweries by name or keyword.
- **Filter by Location**: Find breweries across cities, states/provinces, or countries with optional type filtering (micro, brewpub, regional, cidery).
- **Random Discovery**: Discover unexpected craft breweries worldwide.
- **Zero Authentication**: Completely open and free.

## Endpoints

- `POST /tools/search_breweries`: Search breweries by name.
- `POST /tools/breweries_by_location`: Search breweries by city, state, or country.
- `POST /tools/random_brewery`: Get random breweries.
- `GET /manifest.json`: Omi plugin manifest.
- `GET /.well-known/ai-plugin.json`: OpenAI standard manifest.
- `GET /health`: Service health check.
