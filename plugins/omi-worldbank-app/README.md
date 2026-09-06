# 🌐 World Bank Global Economic & Country Intelligence (Omi Integration App)

An official, zero-authentication Omi integration app providing real-time macroeconomic indicators, national profiles, comparative economics, and geopolitical discovery directly from the official **World Bank Open Data API** (`api.worldbank.org/v2`).

Designed specifically for **Omi AI wearable users**, this integration allows users to query authoritative global data hands-free via voice or chat.

---

## ✨ Features

- **No Auth Required**: 100% public, stable, authoritative data sourced directly from the World Bank Open Data catalog. No API keys, credentials, or OAuth setup needed.
- **Deep Macroeconomic Intelligence**:
  - **Gross Domestic Product (GDP)** & **GDP per Capita**
  - **Annual Inflation Rate (CPI)**
  - **Total Population & Demographics**
  - **Life Expectancy & Human Longevity**
  - **Unemployment Rates**
  - **CO₂ Emissions per Capita**
- **Intelligent Country Alias Resolver**: Supports over 60 common names, abbreviations, and informal country nicknames (e.g. `US`, `USA`, `America`, `Britain`, `UK`, `Bharat`, `Deutschland`, `Korea`), plus automatic fallback to ISO-2/ISO-3 code resolution.
- **Comparative Economic Analysis**: Compares two national economies side-by-side with automatic relative ratio computation (e.g. comparing the US economy to China or India).
- **Voice-Optimized Output**: Formats numerical values with human-friendly units ($27.36T, 1.42B, $81.70K, +3.41%) and structured markdown text tailored for text-to-speech and wearable displays.
- **Omi Chat Tool Protocol Compliant**: Exposes standard `/.well-known/omi-tools.json` manifest with 4 registered tools and strict `ChatToolResponse` models.

---

## 🛠 Registered Omi Tools

| Tool Name | Endpoint | Description |
| :--- | :--- | :--- |
| `get_country_profile` | `POST /tools/country-profile` | Synthesizes an all-in-one economic dossier: capital, region, income level, GDP, inflation, population, and life expectancy. |
| `get_economic_indicator` | `POST /tools/economic-indicator` | Queries a specific macroeconomic indicator with optional multi-year historical trend analysis (1-10 years). |
| `compare_country_economies` | `POST /tools/compare-economies` | Compares two nations across GDP, GDP per capita, inflation, and demographics with relative size insights. |
| `search_countries_by_region` | `POST /tools/search-countries` | Discovers countries matching geographic regions (e.g., *Europe*, *East Asia*) or World Bank income classifications (*High income*, *Lower middle income*). |

---

## 🚀 Quick Start

### 1. Local Installation

```bash
cd plugins/omi-worldbank-app
pip install -r requirements.txt
```

### 2. Run Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Visit `http://localhost:8000` to view the interactive dashboard and documentation, or `http://localhost:8000/.well-known/omi-tools.json` for the Omi tool manifest.

### 3. Run Tests

```bash
# Unit test suite (self-contained, runs with or without virtualenv)
python -m unittest test_main.py

# Live integration smoke test (verifies live World Bank API connectivity)
python smoke_test.py
```

---

## 📡 API Reference & Example Invocations

### 1. Country Profile

**Request:**
```bash
curl -X POST "http://localhost:8000/tools/country-profile" \
     -H "Content-Type: application/json" \
     -d '{"country": "United States"}'
```

**Response:**
```json
{
  "result": "🌍 Country Profile: United States (USA)\n• Capital: Washington, D.C.\n• Region: North America\n• Income Level: High income\n• Coordinates: Lat 38.89, Lon -77.03\n\n📊 Key Macroeconomic Indicators:\n• GDP (Nominal): $27.36T\n• GDP per Capita: $81.70K\n• Inflation Rate: +3.41%\n• Total Population: 334.91M\n• Life Expectancy: 77.50 years",
  "error": null
}
```

---

### 2. Economic Indicator with Trend

**Request:**
```bash
curl -X POST "http://localhost:8000/tools/economic-indicator" \
     -H "Content-Type: application/json" \
     -d '{"country": "India", "indicator": "gdp", "years": 3}'
```

**Response:**
```json
{
  "result": "📈 GDP (current US$) for India (IND):\n• 2023: $3.55T\n• 2022: $3.35T\n• 2021: $3.15T\n\nRecent Annual Change: 🔺 Up 5.97% from 2022 to 2023",
  "error": null
}
```

---

### 3. Compare Economies

**Request:**
```bash
curl -X POST "http://localhost:8000/tools/compare-economies" \
     -H "Content-Type: application/json" \
     -d '{"country_a": "Japan", "country_b": "Germany"}'
```

**Response:**
```json
{
  "result": "⚖️ Economic Comparison: Japan vs Germany\nMetric                    | Japan           | Germany        \n--------------------------|-----------------|----------------\nIncome Level              | High income     | High income    \nRegion                    | East Asia & Pac | Europe & Centra\nGDP (Total)               | $4.21T          | $4.46T         \nGDP Per Capita            | $33.83K         | $52.75K        \nPopulation                | 124.52M         | 84.48M         \nInflation Rate            | +3.27%          | +5.95%         \nLife Expectancy           | 84.6 yrs        | 81.0 yrs       \n\n📌 Insight: Germany's economy is 1.1x the size of Japan's economy.",
  "error": null
}
```

---

### 4. Search & Discovery

**Request:**
```bash
curl -X POST "http://localhost:8000/tools/search-countries" \
     -H "Content-Type: application/json" \
     -d '{"region": "Latin America", "income_level": "Upper middle income", "limit": 5}'
```

---

## ☁️ Deployment

Ready for one-click deployment on **Railway**, **Render**, or **Heroku**:

- **Railway**: Uses the provided `railway.toml` with healthcheck on `/health`.
- **Procfile**: `web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}`
- **Runtime**: Python 3.11 (`runtime.txt`)
