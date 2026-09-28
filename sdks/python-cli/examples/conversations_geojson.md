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

Export your conversation history into JSON:

```bash
# Export recent conversations
omi conversation list --limit 100 --json > conversations.json

# Or export across multiple pages
omi conversation list --limit 100 --offset 0 --json > page1.json
omi conversation list --limit 100 --offset 100 --json > page2.json
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
| `-o, --output` | `conversations.geojson` | Destination GeoJSON file path |
| `--require-coords` | `False` | Only include conversations with valid GPS coordinates |
| `--filter-category`| `None` | Filter by category (e.g. `work`, `personal`, `travel`) |
| `--force` | `False` | Overwrite existing output file if it exists |

---

## 4. Visualizing on Maps

1. **Quick Preview**: Drag and drop your `.geojson` file into [geojson.io](https://geojson.io/).
2. **Interactive 3D Maps**: Upload to [Kepler.gl](https://kepler.gl/demo) to see timeline playback of where your conversations occurred.
3. **Felt / Mapbox**: Import as a vector layer for custom styling and sharing.

---

## 5. Automated Tests

Run the test suite:

```bash
python test_conversations_to_geojson.py
```
