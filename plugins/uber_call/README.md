# Omi Uber Call App

An Omi Chat Tools app that turns a natural-language request such as
“call Uber to the airport” into a ready-to-open Uber deep link.

The app deliberately uses Uber's public mobile deep-link flow instead of the
restricted Ride Request API. That keeps the integration usable without partner
credentials while still letting the user confirm pickup, destination, product,
pricing, and payment inside Uber before any ride is requested.

## What It Does

- Exposes an Omi Chat Tools manifest at `/.well-known/omi-tools.json`
- Provides a `call_uber` tool endpoint at `/api/call_uber`
- Accepts a destination, optional pickup/dropoff coordinates, and optional
  product ID
- Returns both a mobile web link and an app scheme link for Uber
- Fails fast when Omi does not provide a usable destination

## Running Locally

```bash
cd plugins/uber_call
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

## Omi App Store Setup

Create an External Integration app in Omi and set:

- App Home URL: `https://<your-host>`
- Chat Tools Manifest URL: `https://<your-host>/.well-known/omi-tools.json`

After install, the user can ask Omi:

> Call Uber to 1455 Market Street, San Francisco

Omi calls `/api/call_uber` and receives a confirmation-safe link:

```json
{
  "result": "Uber is ready for 1455 Market Street, San Francisco. Open the link to review and confirm the ride in Uber: https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]=1455%20Market%20Street%2C%20San%20Francisco&dropoff[nickname]=1455%20Market%20Street%2C%20San%20Francisco",
  "web_link": "https://m.uber.com/ul/?...",
  "app_link": "uber://?..."
}
```

## Safety And Compliance Notes

- The app does not book rides silently.
- The user must review and confirm the trip in Uber.
- No Uber OAuth token, API key, payment credential, or customer data is stored.
- If Omi provides geolocation, it is only used to prefill pickup coordinates.

## Tests

```bash
python3 -m unittest plugins/uber_call/test_uber_links.py
```

