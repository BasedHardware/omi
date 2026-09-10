# Omi Nearby Places Integration App

Answers everyday location questions — "where is the nearest pharmacy?", "find
an ATM", "is there a cafe around here?" — from OpenStreetMap data. No API key
is required.

## Chat tools

| Tool | What it does |
| --- | --- |
| `find_nearby_places` | Lists the closest places of one category around a location, nearest first, with distance, indicative walking time, address, opening hours, and phone number when OpenStreetMap has them. |
| `find_nearest_place` | Returns only the single closest place, for direct questions like "where is the nearest pharmacy?" |
| `list_place_categories` | Lists every category the app can search for, so the assistant can pick a valid one. |

Supported categories include `pharmacy`, `hospital`, `clinic`, `doctors`,
`dentist`, `atm`, `bank`, `police`, `post_office`, `toilets`, `drinking_water`,
`cafe`, `restaurant`, `fast_food`, `bar`, `supermarket`, `bakery`,
`convenience`, `laundry`, `fuel`, `charging_station`, `parking`,
`bicycle_parking`, `bus_stop`, `train_station`, `taxi`, `hotel`, `library`,
`playground`, `park`, `museum`, `attraction`, `place_of_worship`, and
`recycling`.

Everyday words are accepted as aliases: `drugstore` and `chemist` map to
`pharmacy`, `wc`/`bathroom`/`restroom` to `toilets`, `ev` and `charger` to
`charging_station`, `gas` to `fuel`, `metro` to `train_station`, and so on.

Locations accept a place name, an address, or explicit `lat,lon` coordinates.

## Data sources

- [Nominatim](https://nominatim.openstreetmap.org/) for geocoding.
- [Overpass API](https://overpass-api.de/) for point-of-interest search.

Both are public OpenStreetMap services; the app sends a descriptive
`User-Agent` and issues one request per tool call. Map data © OpenStreetMap
contributors, available under the [ODbL](https://www.openstreetmap.org/copyright).

## Accuracy notes

Distances are straight-line (great-circle) measurements and walking times are
estimates that assume a 25% street detour at 80 m/min. They are deliberately
labelled as estimates rather than routing results.

## Run locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

Then open:

- `http://localhost:8080/` — landing page
- `http://localhost:8080/health` — health check
- `http://localhost:8080/.well-known/omi-tools.json` — chat tool manifest

## Tests

```bash
pip install pytest
python -m pytest test_main.py -q
```

The suite covers category normalization and aliases, coordinate parsing,
distance and walking-time math, Overpass query construction (including that
caller input never reaches the query), result formatting, empty results,
unsupported categories, and upstream failure handling.

## Deployment

The repository deploys plugin apps as containers, so `Procfile`, `railway.toml`,
and `runtime.txt` are included for the same workflow the other integration apps
use. No environment variables or secrets are required.
