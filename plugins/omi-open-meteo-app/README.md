# Open-Meteo Omi App

Check current weather, short forecasts, and basic air-quality readings from Omi conversations.

This is a standalone no-auth Omi app backed by the public Open-Meteo APIs. It does not require environment variables, OAuth, or API keys.

## Tools

- `get_current_weather`: current temperature, wind, humidity, precipitation, and weather condition for a place.
- `get_weather_forecast`: daily forecast for the next 1-7 days.
- `get_air_quality`: current PM2.5, PM10, ozone, nitrogen dioxide, and US AQI where Open-Meteo has data.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Health check:

```bash
curl http://localhost:8080/health
```

Tool manifest:

```bash
curl http://localhost:8080/.well-known/omi-tools.json
```

Example current weather request:

```bash
curl -X POST http://localhost:8080/tools/get_current_weather \
  -H "Content-Type: application/json" \
  -d '{"location":"San Francisco","temperature_unit":"fahrenheit"}'
```

Example forecast request:

```bash
curl -X POST http://localhost:8080/tools/get_weather_forecast \
  -H "Content-Type: application/json" \
  -d '{"location":"London","days":3}'
```

Example air-quality request:

```bash
curl -X POST http://localhost:8080/tools/get_air_quality \
  -H "Content-Type: application/json" \
  -d '{"location":"Berlin"}'
```

## Deployment

Deploy this folder as a standalone FastAPI service. Railway can use `railway.toml`; Heroku-style platforms can use the `Procfile`.

## Notes

- Location lookup uses the Open-Meteo geocoding API and takes the best result.
- Forecast output is capped at 7 days so chat responses stay readable.
- Air-quality values depend on Open-Meteo coverage for the resolved coordinates.
