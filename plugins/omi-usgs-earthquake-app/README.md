# USGS Earthquake Omi Integration

Check recent earthquake activity from Omi chat without connecting an account.

## What it does

- Lists recent earthquakes globally from the USGS public earthquake catalog
- Finds earthquakes near a latitude and longitude within a radius
- Looks up a specific USGS event by event ID
- Returns magnitude, place, time, status, alert level, tsunami flag, felt reports, significance, depth, coordinates, and USGS event links when available

The app uses read-only USGS API calls. No OAuth or API key is required.

## Omi App Configuration

Use these values when creating the Omi app:

| Field | Value |
|-------|-------|
| Chat Tools Manifest URL | `https://YOUR-APP.up.railway.app/.well-known/omi-tools.json` |
| Setup URL | Leave blank |
| Setup Completed URL | Leave blank |

## Chat Tools

| Tool | Endpoint | Purpose |
|------|----------|---------|
| `recent_earthquakes` | `POST /tools/recent_earthquakes` | Find recent earthquakes globally by time window and minimum magnitude |
| `nearby_earthquakes` | `POST /tools/nearby_earthquakes` | Find earthquakes near coordinates within a radius |
| `earthquake_details` | `POST /tools/earthquake_details` | Look up one USGS event by event ID |

## Example prompts

- "Show me earthquakes over magnitude 5 in the last day."
- "Were there any recent earthquakes near 37.77, -122.42?"
- "Look up USGS earthquake event us7000mabc."
- "Find earthquakes within 300 km of Tokyo in the past week."

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Then open:

```text
http://localhost:8080/.well-known/omi-tools.json
```

## Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `USGS_QUERY_URL` | `https://earthquake.usgs.gov/fdsnws/event/1/query` | USGS FDSN event query endpoint |
| `USGS_USER_AGENT` | `OmiUsgsEarthquakeApp/1.0 (https://github.com/BasedHardware/omi)` | Identifies the integration to USGS |
| `USGS_TIMEOUT_SECONDS` | `8` | Request timeout |
| `PORT` | `8080` | Used by Railway and local runs |

## Data Notes

USGS earthquake data can be preliminary and may be revised after review. The app includes that caveat in tool responses so Omi does not present earthquake information as final safety guidance.
