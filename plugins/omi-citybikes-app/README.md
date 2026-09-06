# 🚲 Omi CityBikes Global Micro-Mobility & Transit Integration App

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2.10.4-E92063.svg?logo=pydantic)](https://docs.pydantic.dev)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![API](https://img.shields.io/badge/CityBikes-API%20v2-orange.svg)](https://api.citybik.es/v2/)

Real-time global bike-share and micro-mobility intelligence integration app for the **Omi AI wearable device** ([BasedHardware/omi](https://github.com/BasedHardware/omi)).

Enables Omi users to query live bike availability, locate empty return docks, find nearby stations sorted by GPS distance, and retrieve citywide micro-mobility stats across **800+ bike-share networks in 400+ cities worldwide** (including Citi Bike NYC, Vélib' Métropole Paris, Santander Cycles London, Bicing Barcelona, BIXI Montreal, Divvy Chicago, and more).

---

## 🌟 Features & Voice Capabilities

- **Global Network Discovery**: Search 800+ bike-share networks by city name, country code, or brand name.
- **Real-Time Station Availability**: Live bike counts, empty return docks, and e-bike availability at individual stations.
- **Physical Distance Sorting**: Accurate GPS haversine distance calculation to return the nearest stations in meters/kilometers.
- **Citywide Fleet Overview**: Comprehensive micro-mobility health metrics (total stations, active bikes, dock occupancy ratio, top stations).
- **Production Resilience**: In-memory multi-tier TTL caching (1 hour for network registry, 60 seconds for live station statuses) and sliding-window rate limiting (60 requests/minute/IP).
- **Hermetic Testing**: 100% mocked offline unit test suite + live end-to-end smoke test suite.

---

## 🛠️ Registered Omi Chat Tools

Exposed via `/.well-known/omi-tools.json`:

| Tool Endpoint | Tool Name | Voice Prompts / Usage |
|---|---|---|
| `POST /tools/search_bike_networks` | `search_bike_networks` | *"Find bike sharing networks in Paris"*, *"Is Citi Bike supported?"* |
| `POST /tools/get_nearby_bike_stations` | `get_nearby_bike_stations` | *"Are there bikes available near Broadway?"*, *"Find nearest station to my GPS coords"* |
| `POST /tools/check_bike_station_status` | `check_bike_station_status` | *"Check status of Grand Central bike station"*, *"How many empty docks at Station 102?"* |
| `POST /tools/get_city_bike_overview` | `get_city_bike_overview` | *"How many bikes are available across Barcelona right now?"*, *"Give me a summary of Citi Bike"* |

---

## 📡 API Endpoints

### 1. Root Landing Page
- **`GET /`**: HTML dashboard showcasing service capabilities and tool catalog.

### 2. Health Check
- **`GET /health`**: Health status for container orchestrators and load balancers.
```json
{
  "status": "ok",
  "service": "omi-citybikes-app"
}
```

### 3. Omi Manifest
- **`GET /.well-known/omi-tools.json`**: Official Omi plugin discovery specification.

### 4. Search Networks
- **`POST /tools/search_bike_networks`**
```json
// Request
{
  "query": "Paris",
  "limit": 3
}

// Response
{
  "result": "Found 1 bike network(s) matching 'Paris':\n1. **Vélib' Métropole** (Paris, FR)\n   - Network ID: `velib-metropole`",
  "error": null
}
```

### 5. Nearby Stations
- **`POST /tools/get_nearby_bike_stations`**
```json
// Request
{
  "network_id": "citi-bike-nyc",
  "query": "Broadway",
  "latitude": 40.7527,
  "longitude": -73.9772,
  "limit": 3
}

// Response
{
  "result": "### 🚲 Bike Stations: Citi Bike (New York, NY)\n\n1. **Broadway & W 42nd St** · 350m away\n   - **14 bikes available**, 16 empty docks\n2. **Broadway & E 14th St** · 2.1km away\n   - **6 bikes available**, 24 empty docks",
  "error": null
}
```

### 6. Station Status
- **`POST /tools/check_bike_station_status`**
```json
// Request
{
  "network_id": "citi-bike-nyc",
  "station_id_or_name": "Grand Central"
}

// Response
{
  "result": "## 🚲 Station Status: Grand Central Terminal - 42nd St\n**Network**: Citi Bike (New York, NY)\n- **Available Bikes**: 22\n  *Includes E-Bikes*: 8\n- **Empty Return Docks**: 8\n- **Total Capacity**: 30 docks\n\n*Last updated*: 2026-09-06 18:00:00 UTC",
  "error": null
}
```

### 7. City Overview
- **`POST /tools/get_city_bike_overview`**
```json
// Request
{
  "city_or_network": "Barcelona"
}

// Response
{
  "result": "## 🚲 Micro-Mobility Overview: Bicing (Barcelona)\n- **Active Stations**: 519\n- **Available Bikes Fleet**: 3,842\n- **Empty Return Docks**: 3,120\n- **Network Availability**: 55.2% of docks holding bikes\n\n### Top Stations with High Availability:\n- **Plaza Catalunya**: 32 bikes available\n- **Passeig de Gracia**: 28 bikes available",
  "error": null
}
```

---

## 🚀 Quickstart & Development

### Using `uv` (Recommended)
```bash
# Run tests
uv run --with fastapi --with httpx --with pydantic python -m unittest test_main.py -v

# Run live smoke test
uv run --with fastapi --with httpx --with pydantic python smoke_test.py

# Start local server
uv run --with fastapi --with httpx --with uvicorn --with pydantic uvicorn main:app --reload --port 8000
```

### Using standard `pip`
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Using Docker
```bash
docker build -t omi-citybikes-app .
docker run -p 8000:8000 omi-citybikes-app
```

---

## 🧪 Testing

### 1. Hermetic Unit Tests (100% Mocked)
Runs without network access in under 1 second:
```bash
python -m unittest test_main.py -v
```

### 2. Live Smoke Tests (End-to-End)
Verifies live connectivity against `https://api.citybik.es/v2`:
```bash
python smoke_test.py
```

---

## 🚢 Deployment

### Deploy to Railway
Push to GitHub and create a new Railway service pointing to `plugins/omi-citybikes-app/` using the included `railway.toml` and `Dockerfile`.

### Deploy to Render / Heroku
Uses the included `Procfile` and `runtime.txt` to automatically bind to `$PORT`.
