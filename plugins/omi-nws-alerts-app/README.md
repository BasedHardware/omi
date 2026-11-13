# National Weather Service (NWS) Severe Weather Alerts Omi Integration Plugin

[![Omi Integration](https://img.shields.io/badge/Omi-Plugin-blue.svg)](https://github.com/BasedHardware/omi)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-brightgreen.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg)](https://fastapi.tiangolo.com/)

Official National Oceanic and Atmospheric Administration (NOAA) / National Weather Service (NWS) real-time severe weather warning, storm tracking, and protective safety action intelligence for Omi wearable AI devices (glasses, necklaces, and audio wearables).

---

## Features & Omi Chat Tools

This plugin exposes three unauthenticated, life-safety function-calling tools via `/.well-known/omi-tools.json`:

1. **`get_active_alerts_by_location`** (`POST /tools/get-active-alerts-by-location`)
   - Checks for active severe weather warnings, tornado watches, flood alerts, and advisories for a specific GPS coordinate pair (latitude, longitude).
   - Returns severity rankings, certainty, urgency, affected counties/cities, and protective safety instructions (e.g. taking shelter, avoiding floodwaters).

2. **`get_active_alerts_by_state`** (`POST /tools/get-active-alerts-by-state`)
   - Retrieves active warnings and watches for any US state or territory (e.g. `"TX"`, `"CA"`, `"Florida"`).
   - Normalizes state names and postal abbreviations to USPS standard codes.
   - Highlights the highest-severity hazards first, with optional severity filters.

3. **`get_national_severe_weather_summary`** (`POST /tools/get-national-severe-weather-summary`)
   - Delivers a nationwide tactical weather overview, tracking total active emergencies across the United States.
   - Categorizes life-threatening (Extreme) and severe hazards, listing active emergencies like tornadoes, blizzards, hurricanes, or severe flash floods.

---

## Production Hardening & Architecture

- **Zero-Authentication Architecture**: Directly integrates with the official National Weather Service Open API (`https://api.weather.gov`) with zero API keys or user logins required.
- **Bounded LRU Cache with Deep-Copy Mutation Isolation**: In-memory cache capped at 1,000 entries with a 120-second TTL for active weather feeds, ensuring freshness while shielding upstream NOAA endpoints.
- **Sliding-Window Rate Limiting**: 60 requests/minute per client IP with trusted proxy `X-Forwarded-For` CIDR isolation to prevent IP spoofing.
- **Cached Upstream Health Probing**: `/health` verifies upstream NOAA status by polling active alert counts with a 60-second cached TTL, ensuring zero quota depletion.
- **Hermetic Tests**: 100% offline unit suite running in ~0.5s with zero network dependencies or `time.sleep` blocking.

---

## Local Development & Testing

### Installation

```bash
cd plugins/omi-nws-alerts-app
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
```

### Run Hermetic Unit Tests

```bash
pytest test_main.py -v
```

### Run Live End-to-End Smoke Tests

```bash
python smoke_test.py
```

### Run Locally

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

---

## Deployment

Deployable to Railway, Render, Heroku, or any standard container platform:

- **Procfile**: `web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}`
- **railway.toml**: Nixpacks deployment with healthcheck path `/health`
- **Environment Variables**:
  - `NWS_API_BASE_URL`: Base URL for NWS API (default `https://api.weather.gov`)
  - `NWS_USER_AGENT`: Custom User-Agent header (required by NOAA API policy)
  - `NWS_REQUEST_TIMEOUT`: Outbound HTTP request timeout in seconds (default `10.0`)
