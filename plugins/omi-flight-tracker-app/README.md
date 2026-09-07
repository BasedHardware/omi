# ✈️ Omi Live Aviation Radar & Flight Tracker Integration App

An authoritative, zero-authentication **Live Flight Tracker & Aviation Radar** integration app for **Omi AI Wearables** (Glasses, Necklaces, and Audio Devices), built under **Issue [#3120](https://github.com/BasedHardware/omi/issues/3120)**.

Powered by real-time ADS-B transponder telemetry from the [OpenSky Network](https://opensky-network.org/), this plugin brings real-time aerial intelligence directly to wearable users looking up at the sky.

---

## 🌟 Why This is a Killer App for Wearables

When wearing an Omi AI pendant or smart glasses outdoors:
- 👂 **Hear a plane overhead?** Ask: *"What plane is flying overhead right now?"*  
  Omi calculates the exact aircraft callsign, airline, altitude, ground speed, and tells you where to look (*"Flight UAL123 is 2.4 miles to your North-East at 32,000 feet, cruising at 480 mph"*).
- 🛫 **Tracking family or friends?** Ask: *"Track flight BAW28"*  
  Omi reports live coordinates, rate of climb/descent, and whether the flight is cruising or approaching an airport.
- 🌐 **Curious about regional skies?** Ask: *"How many planes are currently in the sky above Frankfurt / London?"*  
  Omi returns an instant air traffic summary with active airborne vs. on-ground flight counts.

---

## 🛠️ Registered Omi Chat Tools

All tools are registered in the official Omi manifest at `/.well-known/omi-tools.json` and follow the strict `ChatToolResponse(result=..., error=...)` protocol:

| Endpoint | Tool Name | Voice Prompts & Use Cases |
|---|---|---|
| `POST /tools/get_flights_overhead` | `get_flights_overhead` | *"What plane is flying overhead right now?"*, *"Find flights near Central Park within 30km"* |
| `POST /tools/track_flight_by_callsign` | `track_flight_by_callsign` | *"Where is flight DLH400 right now?"*, *"Track flight UAL123"* |
| `POST /tools/get_airspace_activity` | `get_airspace_activity` | *"Air traffic report for Tokyo area"*, *"How many aircraft are flying over the UK right now?"* |

---

## 🏗️ Architecture & Production Hardening

1. **100% Zero-Authentication**:
   - Sourced directly from OpenSky Network's public ADS-B REST API.
   - Requires zero user registration, API keys, or OAuth flows.
2. **Aviation Mathematics**:
   - **Haversine Distance**: Great-circle observer-to-aircraft distance in both kilometers and statute miles.
   - **Compass Bearing**: Normalized 16-point cardinal compass directions (N, NNE, NE, E, etc.).
   - **Vertical Velocity**: Telemetric climb and descent rate analysis (e.g. `Climbing (+1,800 ft/min)` or `Level Flight (Cruising)`).
   - **City Registry**: Built-in support for 25+ major global aviation metropolises and coordinate resolution.
3. **Resilient LRU Caching**:
   - Bounded `collections.OrderedDict` with recency promotion on hits and deep-copy mutation isolation.
   - 15-second TTL matching OpenSky's sensor ingestion rate, preventing 429 throttling.
4. **Sliding-Window Rate Limiting with Proxy Protection**:
   - In-memory 60 req/min sliding-window limiter per client IP.
   - Safe `X-Forwarded-For` inspection restricted strictly to configured `TRUSTED_PROXIES` (preventing IP spoofing).
5. **Container Security**:
   - Hardened `Dockerfile` running as non-root `appuser`.
   - Lightweight container base with automated health checks.

---

## 🚀 Quickstart & Local Development

### 1. Installation

```bash
cd plugins/omi-flight-tracker-app
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
```

### 2. Run the Server

```bash
uvicorn main:app --reload --port 8000
```

- **Interactive Dashboard**: Open [http://localhost:8000/](http://localhost:8000/)
- **Omi Manifest**: [http://localhost:8000/.well-known/omi-tools.json](http://localhost:8000/.well-known/omi-tools.json)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🧪 Verification & Testing

### Hermetic Unit Tests (100% Offline & Mocked)

Runs 29 hermetic unit tests with 0 network I/O in < 3 seconds:

```bash
python -m pytest test_main.py -v
# Or using standard unittest:
python -m unittest test_main.py
```

### Live Smoke Tests

Verifies real-time connectivity against live `opensky-network.org` APIs:

```bash
python smoke_test.py
```

---

## 🚢 Deployment

### Railway (One-Click)

The repository includes `railway.toml` with automated Nixpacks build and `/health` probe configuration.

### Docker

```bash
docker build -t omi-flight-tracker-app .
docker run -p 8000:8000 omi-flight-tracker-app
```

---

## 📜 Bounty & Attribution

- **Bounty**: $50 (Issue [#3120](https://github.com/BasedHardware/omi/issues/3120))
- **Claim**: `/claim #3120`
- **Contributor**: `@ranadheer-designs`
