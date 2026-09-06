# Omi Met Museum Art Collection Integration Plugin 🏛️🎨

An integration microservice for the [Omi wearable ecosystem](https://github.com/BasedHardware/omi) that brings over **470,000 works of art** spanning **5,000 years of human history** directly to your AI wearable via [The Metropolitan Museum of Art Collection API](https://metmuseum.github.io/).

---

## Features

- 🔍 **Artwork Discovery**: Search through masterworks by keyword, artist, or culture with filters for digital imagery and curatorial departments.
- 🖼️ **In-Depth Artwork Details**: Retrieve artist biographies, culture, period, creation dates, mediums, dimensions, high-resolution primary images, and direct museum links.
- 🏛️ **Curatorial Departments**: Browse all 19 curatorial departments at The Met (European Paintings, Egyptian Art, Asian Art, Arms and Armor, Photographs, etc.).
- ⭐ **Department Masterpieces**: Fetch curated highlights and iconic masterworks from any Met curatorial department.
- ⚡ **Production-Ready & Hardened**:
  - Sliding-window in-memory rate limiting with secure proxy header (`X-Forwarded-For`) validation against `TRUSTED_PROXIES`.
  - Bounded memory storage with automatic purge of idle IP entries.
  - Thread-safe true LRU caching (`collections.OrderedDict`) with recency promotion on hits and deep copies to prevent cache mutation.
  - Safe Dockerfile containerization running as an unprivileged user (`appuser`).
  - Comprehensive unit test suite and live integration smoke test suite.

---

## Omi Tools Manifest (`/.well-known/omi-tools.json`)

The service provides an OpenAI-compatible function calling manifest:

| Function Name | Description | Required Arguments |
|---|---|---|
| `search_artworks` | Search artworks by keyword, artist, or culture | `query` |
| `get_artwork_details` | Get full details for an artwork by object ID | `object_id` |
| `list_departments` | List all 19 curatorial departments with IDs | *(none)* |
| `get_department_highlights` | Fetch curated masterwork highlights from a department | `department_id` |

---

## Example Usage

### 1. Search Artworks
```bash
curl -X POST "http://localhost:8080/tools/search-artworks" \
     -H "Content-Type: application/json" \
     -d '{"query": "Water Lilies", "limit": 3}'
```

### 2. Get Artwork Details
```bash
curl -X POST "http://localhost:8080/tools/get-artwork-details" \
     -H "Content-Type: application/json" \
     -d '{"object_id": 437112}'
```

### 3. List Departments
```bash
curl -X POST "http://localhost:8080/tools/list-departments" \
     -H "Content-Type: application/json" \
     -d '{}'
```

### 4. Get Department Highlights
```bash
curl -X POST "http://localhost:8080/tools/get-department-highlights" \
     -H "Content-Type: application/json" \
     -d '{"department_id": 11, "limit": 3}'
```

---

## Local Development & Testing

### Running with Python
```bash
cd plugins/omi-met-museum-app
pip install -r requirements.txt
python main.py
```

### Running Unit Tests
```bash
pytest test_main.py -v
```

### Running Live Smoke Tests
```bash
python smoke_test.py
```

### Running with Docker
```bash
docker build -t omi-met-museum-app .
docker run -p 8080:8080 omi-met-museum-app
```
