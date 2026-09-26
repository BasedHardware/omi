# Omi REST Countries & Global Geographic Intelligence App

A standalone, no-authentication Omi Chat Tool plugin that brings instant global country profiles, capital city discovery, regional border analysis, currency/language queries, and demographic comparisons to Omi AI wearables.

Built for zero-latency voice interactions with **zero OAuth tokens or API keys required**.

---

## Features

- **Detailed Country Profiles**: Complete demographic and geographic facts (common/official name, capital, population, surface area, currency, languages, demonym, ISO codes, and flag emojis).
- **Capital City Discovery**: Resolve which country has a specific capital city (e.g. *"What country has the capital Canberra?"*).
- **Regional Border Analysis**: List all neighboring countries sharing land borders with any nation, with special handling for island states (e.g. Japan, Australia, Iceland).
- **Currency & Language Cross-Queries**: Find all countries using a specific currency (e.g. `EUR`, `USD`, `Yen`, `Franc`) or speaking an official language (e.g. Spanish, Arabic, French, German).
- **Side-by-Side Country Comparisons**: Compare population differences and land mass between any two countries for immediate wearable answers.
- **Voice-Friendly Audio Formatting**: Clear, concise responses optimized for wearable audio prompts without noisy markdown walls.
- **Resilient & Hermetic**: High-performance in-memory TTL caching (`SimpleTTLCache`) and bounded lookups.
- **Strict Omi Chat Tool Contract**: Full compliance with `/.well-known/omi-tools.json` manifest (`endpoint`, `method: "POST"`), `ChatToolResponse(result=...)` or `ChatToolResponse(error=...)`, with automatic exclusion of `null` fields.

---

## Registered Chat Tools

| Tool Name | Endpoint | Method | Description |
| :--- | :--- | :--- | :--- |
| `get_country_info` | `/tools/get_country_info` | `POST` | Comprehensive country facts by name, alias, or ISO 2/3 code. |
| `search_by_capital` | `/tools/search_by_capital` | `POST` | Find which country has a given capital city. |
| `get_border_countries` | `/tools/get_border_countries` | `POST` | List neighboring nations sharing land borders. |
| `search_by_currency` | `/tools/search_by_currency` | `POST` | Discover countries utilizing a specific currency. |
| `search_by_language` | `/tools/search_by_language` | `POST` | Discover countries speaking a specific language. |
| `compare_countries` | `/tools/compare_countries` | `POST` | Compare population and geographic area between two countries. |

---

## Example Responses

### `get_country_info`
**Request:**
```json
{
  "country": "France"
}
```
**Response:**
```json
{
  "result": "🇫🇷 **France** (French Republic)\n• **Capital:** Paris\n• **Region:** Europe (Western Europe)\n• **Population:** 68,688,000 (Demonym: French)\n• **Area:** 551,695.0 km²\n• **Currency:** Euro (€) [EUR]\n• **Languages:** French\n• **Borders:** 8 neighboring countries: Andorra, Belgium, Germany, Italy, Luxembourg, Monaco and 2 more\n• **ISO Codes:** FR / FRA"
}
```

### `compare_countries`
**Request:**
```json
{
  "country_a": "Japan",
  "country_b": "Germany"
}
```
**Response:**
```json
{
  "result": "📊 **Comparison: 🇯🇵 Japan vs 🇩🇪 Germany**\n\n• **Population:** 123,300,000 vs 83,517,030\n  ↳ Japan has 39,782,970 more residents.\n• **Area:** 377,930.0 km² vs 357,114.0 km²\n  ↳ Japan is larger by 20,816.0 km².\n• **Capital:** Tokyo vs Berlin\n• **Region:** Asia (Eastern Asia) vs Europe (Western Europe)\n• **Languages:** Japanese vs German"
}
```

---

## Verification & Testing

- **Syntax & Bytecode Validation**:
  ```bash
  python -m py_compile data.py models.py main.py test_main.py smoke_test.py
  ```
  *(0 compilation errors)*

- **Hermetic Unit Test Suite**:
  ```bash
  python -m unittest test_main.py
  ```
  *(28/28 passing in 0.027s)*

- **ASGI Integration Smoke Tests**:
  ```bash
  python smoke_test.py
  ```
  *(9/9 passing)*

---

## Deployment

Deployable directly via Docker, Nixpacks, Railway, or Heroku:
- `railway.toml`: Automated nixpacks configuration with failure restart policy.
- `Procfile`: `web: uvicorn main:app --host 0.0.0.0 --port $PORT`
- `runtime.txt`: `python-3.11`
- `requirements.txt`: Pinned versions matching sibling Omi plugins (`fastapi==0.115.6`, `uvicorn[standard]==0.34.0`, `httpx==0.28.1`, `pydantic==2.10.4`).
