# World Time & Solar Ephemeris Omi App

Live global time, timezone conversions, time difference calculations, sunrise/sunset, and solar ephemeris for Omi AI wearable devices.

This is a standalone, no-auth Omi chat tool integration powered by Python's IANA timezone database (`zoneinfo`), the public Open-Meteo Geocoding service, and the open Sunrise-Sunset API. It requires **no API keys, user accounts, or environment variables**.

---

## Features & Chat Tools

- **`get_current_time`**: Current time in 12-hour and 24-hour formats, local date, day of week, timezone abbreviation, UTC offset (e.g. `UTC+09:00`), and Daylight Saving Time (DST) status for any city or IANA timezone.
- **`calculate_time_difference`**: Instant timezone conversion between two global locations, exact hour/minute difference (e.g. *"Tokyo is 13 hours ahead of New York"*), and calendar day offset. Supports converting arbitrary user times or current time.
- **`get_solar_times`**: Precise sunrise, sunset, solar noon, day length, and civil twilight (dawn / first light and dusk / last light) converted into local time for any city worldwide.

---

## Voice Prompts Supported by Omi

Users wearing Omi devices can naturally ask:

- *"What time is it in Tokyo right now?"*
- *"What's the time difference between New York and London?"*
- *"If it's 3:00 PM in San Francisco, what time is it in Paris?"*
- *"When does the sun set in Paris today?"*
- *"How many hours of daylight do we have in Sydney today?"*
- *"What time is first light tomorrow in Honolulu?"*

---

## Local Development & Testing

### 1. Set Up Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Server
```bash
uvicorn main:app --reload --port 8080
```

### 3. Check Health & Tool Manifest
```bash
# Health check
curl http://localhost:8080/health

# Omi chat tools manifest
curl http://localhost:8080/.well-known/omi-tools.json
```

### 4. Run Automated Tests
```bash
# Run hermetic unit test suite
python3 -m unittest test_main.py

# Run live integration smoke tests
python3 smoke_test.py
```

---

## Example Tool Invocations

### 1. Get Current Time
```bash
curl -X POST http://localhost:8080/tools/get_current_time \
  -H "Content-Type: application/json" \
  -d '{"location": "Tokyo"}'
```
**Sample Response:**
```json
{
  "result": "Current time in Tokyo, Japan (Asia/Tokyo):\n• Local Time: 09:15:30 PM (21:15:30)\n• Date: Tuesday, September 8, 2026\n• Timezone: JST (UTC+09:00)\n• Daylight Saving Time (DST): Inactive",
  "error": null
}
```

### 2. Convert Time & Calculate Difference
```bash
curl -X POST http://localhost:8080/tools/calculate_time_difference \
  -H "Content-Type: application/json" \
  -d '{
    "source_location": "New York",
    "target_location": "Tokyo",
    "source_time": "14:00"
  }'
```
**Sample Response:**
```json
{
  "result": "Time Comparison:\n• Difference: Tokyo is 13 hours ahead of New York\n• New York: 02:00 PM (14:00) EDT on Tuesday, Sep 8, 2026\n• Tokyo: 03:00 AM (03:00) JST on Wednesday, Sep 9, 2026 (+1 day, tomorrow)",
  "error": null
}
```

### 3. Get Solar Ephemeris (Sunrise & Sunset)
```bash
curl -X POST http://localhost:8080/tools/get_solar_times \
  -H "Content-Type: application/json" \
  -d '{
    "location": "Paris",
    "date": "2026-09-08"
  }'
```
**Sample Response:**
```json
{
  "result": "Solar Ephemeris for Paris, France on 2026-09-08:\n• Sunrise: 07:18 AM CEST\n• Sunset: 08:19 PM CEST\n• Solar Noon: 01:48 PM CEST\n• Day Length: 13h 01m\n• Dawn (First Light): 06:46 AM CEST\n• Dusk (Last Light): 08:51 PM CEST",
  "error": null
}
```

---

## Architecture & Reliability

- **Standard Library Precision**: Time calculations and conversions are powered by Python's built-in `zoneinfo` and the standard IANA timezone database.
- **In-Memory LRU Caching**: Bounded TTL cache (`SimpleTTLCache`) eliminates redundant geocoding queries and protects downstream services.
- **Omi Chat-Tool Protocol Compliant**: Exposes `/.well-known/omi-tools.json` function manifest with JSON schema validation and structured `ChatToolResponse` error handling.
- **Ready for Deployment**: Includes `railway.toml` (Nixpacks), `Procfile`, and `runtime.txt` (`python-3.11`).
