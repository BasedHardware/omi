"""Hermetic regression test: optional tool parameters sent as JSON null must take
their defaults instead of failing validation.

The Omi backend builds every non-required manifest parameter as
Optional[...] with default None and, with the pinned langchain-core 1.3.3,
forwards those defaulted fields in the request body. So "what is the weather in Berlin?"
reaches this app as {"location": "Berlin", "temperature_unit": null}.
The request models previously typed temperature_unit and days as plain types without
null-coercion, pydantic rejected the null, and calls failed with 422.

Drives the real FastAPI app with mocked Open-Meteo responses. Zero external network calls.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient

# Mock data
FAKE_PLACE = {
    "id": 2950159,
    "name": "Berlin",
    "latitude": 52.52437,
    "longitude": 13.41053,
    "admin1": "State of Berlin",
    "country": "Germany"
}

FAKE_CURRENT_WEATHER = {
    "latitude": 52.52,
    "longitude": 13.41,
    "timezone": "Europe/Berlin",
    "utc_offset_seconds": 7200,
    "current_units": {
        "time": "iso8601",
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "apparent_temperature": "°C",
        "precipitation": "mm",
        "weather_code": "wmo code",
        "wind_speed_10m": "km/h"
    },
    "current": {
        "time": "2026-09-18T12:00",
        "temperature_2m": 18.5,
        "relative_humidity_2m": 55,
        "apparent_temperature": 18.0,
        "precipitation": 0.0,
        "weather_code": 1,
        "wind_speed_10m": 12.3
    }
}

FAKE_FORECAST = {
    "latitude": 52.52,
    "longitude": 13.41,
    "timezone": "Europe/Berlin",
    "utc_offset_seconds": 7200,
    "daily_units": {
        "time": "iso8601",
        "weather_code": "wmo code",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_probability_max": "%",
        "wind_speed_10m_max": "km/h"
    },
    "daily": {
        "time": ["2026-09-18", "2026-09-19", "2026-09-20"],
        "weather_code": [1, 2, 3],
        "temperature_2m_max": [20.1, 21.3, 19.5],
        "temperature_2m_min": [11.2, 12.0, 10.8],
        "precipitation_probability_max": [10, 25, 60],
        "wind_speed_10m_max": [14.0, 15.2, 18.1]
    }
}

FAKE_AIR_QUALITY = {
    "latitude": 52.52,
    "longitude": 13.41,
    "current_units": {
        "time": "iso8601",
        "european_aqi": "EAQI",
        "us_aqi": "USAQI",
        "pm10": "μg/m³",
        "pm2_5": "μg/m³",
        "ozone": "μg/m³"
    },
    "current": {
        "time": "2026-09-18T12:00",
        "european_aqi": 22,
        "us_aqi": 35,
        "pm10": 12.5,
        "pm2_5": 8.1,
        "ozone": 45.0
    }
}


def fake_request_json(client, url, params):
    if "forecast" in url:
        if "daily" in params:
            return FAKE_FORECAST
        return FAKE_CURRENT_WEATHER
    if "air-quality" in url:
        return FAKE_AIR_QUALITY
    raise ValueError(f"Unexpected url: {url}")


async def fake_resolve_location(client, location):
    if location == "invalid_place_xyz":
        return None, f"no Open-Meteo geocoding result for '{location}'"
    return FAKE_PLACE, None


class NullOptionalParametersTakeDefaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import meteo_main
        cls.meteo_main = meteo_main

    def setUp(self):
        self.patcher1 = patch.object(self.meteo_main, "_resolve_location", side_effect=fake_resolve_location)
        self.patcher2 = patch.object(self.meteo_main, "_request_json", side_effect=fake_request_json)
        self.patcher1.start()
        self.patcher2.start()
        self.addCleanup(self.patcher1.stop)
        self.addCleanup(self.patcher2.stop)
        self.client = TestClient(self.meteo_main.app)

    def test_current_weather_with_null_unit_uses_celsius(self):
        response = self.client.post("/tools/get_current_weather", json={"location": "Berlin", "temperature_unit": None})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Current weather for Berlin", data.get("result", ""))
        self.assertIn("Temperature: 18.5°C", data.get("result", ""))

    def test_forecast_with_null_days_and_unit_uses_defaults(self):
        response = self.client.post("/tools/get_weather_forecast", json={"location": "Berlin", "days": None, "temperature_unit": None})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("3-day forecast for Berlin", data.get("result", ""))

    def test_forecast_with_explicit_parameters(self):
        response = self.client.post("/tools/get_weather_forecast", json={"location": "Berlin", "days": 3, "temperature_unit": "fahrenheit"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("3-day forecast for Berlin", data.get("result", ""))

    def test_air_quality_with_valid_location(self):
        response = self.client.post("/tools/get_air_quality", json={"location": "Berlin"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Air quality for Berlin", data.get("result", ""))

    def test_validation_error_returns_chat_tool_response_error(self):
        # Missing required 'location' parameter
        response = self.client.post("/tools/get_current_weather", json={"temperature_unit": "celsius"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("result"))
        self.assertIn("invalid tool request", data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
