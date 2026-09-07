# NASA Space & Astronomy Intelligence Omi Integration Plugin

[![Omi Integration](https://img.shields.io/badge/Omi-Plugin-blue.svg)](https://github.com/BasedHardware/omi)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-brightgreen.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688.svg)](https://fastapi.tiangolo.com/)

Provides real-time cosmological insights, NASA Astronomy Picture of the Day (APOD), Near-Earth Asteroid (NEO) tracking, and official mission archives for Omi wearable devices.

---

## Features & Omi Chat Tools

This plugin exposes three unauthenticated, high-utility function-calling tools via `/.well-known/omi-tools.json`:

1. **`get_astronomy_picture`** (`POST /tools/get-astronomy-picture`)
   - Retrieves NASA's official Astronomy Picture of the Day (APOD) with expert cosmological explanation, title, photographer credit, and high-res imagery.
   - Supports historical queries via `date` (YYYY-MM-DD).

2. **`get_near_earth_asteroids`** (`POST /tools/get-near-earth-asteroids`)
   - Live tracking of asteroids passing by Earth today via NASA NeoWs (Near Earth Object Web Service).
   - Provides estimated diameters (meters), relative velocities (km/h), close approach miss distances (km), and hazard status.

3. **`search_nasa_media`** (`POST /tools/search-nasa-media`)
   - Searches NASA's official 140,000+ photo and mission archive (Hubble, James Webb Space Telescope, Mars rovers, Apollo, nebulae, exoplanets).
   - Returns mission summaries, NASA IDs, capture dates, and image preview links.

---

## Production Hardening & Resilience

- **Zero-Auth Architecture**: Leverages NASA's public open APIs (`api.nasa.gov` with public `DEMO_KEY` fallback, and `images-api.nasa.gov` which requires zero keys).
- **Bounded LRU Cache with Deep-Copy Isolation**: Prevents cache-poisoning mutations and limits memory to 1,000 items with time-to-live expiration.
- **Sliding-Window Rate Limiter**: Maximum 60 requests/minute per client IP with trusted proxy `X-Forwarded-For` isolation and private subnet detection.
- **Cached Upstream Health Probing**: Periodic `/health` probe verifies upstream connectivity with a 60-second negative/positive cache.
- **Hermetic Tests**: 100% offline unit suite running in ~0.5s without live network calls or `time.sleep` delays.

---

## Local Development & Testing

### Installation

```bash
cd plugins/omi-nasa-space-app
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

### Run Service Locally

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

---

## Deployment

Deployable to Railway, Heroku, or any standard container environment:

- **Procfile**: `web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}`
- **railway.toml**: Nixpacks deployment with healthcheck path `/health`
- **Environment Variables**:
  - `NASA_API_KEY`: Optional custom NASA API key (defaults to `DEMO_KEY`)
  - `MET_API_TIMEOUT`: Outbound HTTP request timeout in seconds (default `10.0`)
