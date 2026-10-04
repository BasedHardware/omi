# Export conversations to GeoJSON (Map / GIS)

Use this recipe to export Omi conversations into a standard [GeoJSON](https://geojson.org/)
FeatureCollection ([RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946)).

This allows you to visualize your conversations, meetings, and life-logs on
interactive maps using [Kepler.gl](https://kepler.gl/), [QGIS](https://qgis.org/),
[Felt](https://felt.com/), [geojson.io](https://geojson.io/), Mapbox, or Google Earth.

Each conversation with location data is mapped to a Point feature with longitude,
latitude, and optional altitude. Feature properties include conversation ID,
title, category, timestamps, duration, location name, address, overview summary,
and transcript snippet. It requires zero external dependencies (pure Python
standard library), supports multi-page exports with automatic ID deduplication,
and protects against path traversal.

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

---

## 1. Export conversations from Omi

Export your conversation history into JSON (note that `--json` is a global flag before the verb):

```bash
# Export conversations
omi --json conversation list --limit 100 --offset 0 > conversations.json

# Or export across multiple pages
omi --json conversation list --limit 100 --offset 0 > page1.json
omi --json conversation list --limit 100 --offset 100 > page2.json
```

---

## 2. Generate the GeoJSON file

Run `conversations_to_geojson.py` against your exported files:

```bash
# Basic export (all conversations)
python conversations_to_geojson.py conversations.json -o life_map.geojson

# Only include conversations with valid GPS coordinates
python conversations_to_geojson.py conversations.json \
  -o life_map_geo.geojson \
  --require-coords

# Filter by category (e.g. only 'travel' or 'work' meetings)
python conversations_to_geojson.py conversations.json \
  -o travel_map.geojson \
  --filter-category travel \
  --require-coords

# Combine multiple files with automatic deduplication
python conversations_to_geojson.py page1.json page2.json -o life_map_all.geojson
```

---

## 3. Command options

| Option | Default | Description |
| :--- | :--- | :--- |
| `-o, --output` | `conversations.geojson` | Path to save the resulting GeoJSON file |
| `--require-coords` | `False` | Only output features with valid GPS coordinates |
| `--filter-category`| `None` | Filter conversations by category (e.g. `work`, `travel`) |
| `--force` | `False` | Overwrite the output file if it already exists |

---

## 4. Visualizing your Map

1. **geojson.io**: Open [geojson.io](https://geojson.io/) and drag-and-drop `life_map.geojson` directly onto the map.
2. **Kepler.gl**: Go to [kepler.gl/demo](https://kepler.gl/demo) and upload your file for interactive geospatial analytics and 3D point clustering.
3. **QGIS**: Open QGIS, choose `Layer -> Add Layer -> Add Vector Layer...` and select `life_map.geojson`.

---

## 5. Automated Tests

Run the test suite:

```bash
python -m pytest tests/test_conversations_to_geojson.py
```
