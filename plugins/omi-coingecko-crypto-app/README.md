# CoinGecko Crypto & Market Intelligence Omi App

Live cryptocurrency prices, token search, market capitalization rankings, and trending coins for Omi AI wearable devices.

This is a standalone, no-auth Omi chat tool integration powered by CoinGecko's public REST API. It requires no API keys, accounts, or complex setup.

---

## Features & Chat Tools

- **`get_crypto_price`**: Real-time price quote, 24-hour percentage change, 24-hour trading volume, and market cap for one or more cryptocurrencies. Supports fiat conversion (`usd`, `eur`, `gbp`, `jpy`, etc.).
- **`search_crypto_coins`**: Fast coin search by ticker symbol or name (e.g. `sol`, `doge`, `pepe`) returning official CoinGecko IDs and global market cap rank.
- **`get_trending_crypto`**: Discover the top searched and trending cryptocurrencies worldwide over the past 24 hours.
- **`get_crypto_market_overview`**: Top global cryptocurrencies ranked by market cap with snapshot metrics.

---

## Local Development & Testing

### 1. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the Server
```bash
uvicorn main:app --reload --port 8080
```

### 3. Check Health & Manifest
```bash
# Health check
curl http://localhost:8080/health

# Tool manifest
curl http://localhost:8080/.well-known/omi-tools.json
```

---

## Example Usage

### 1. Get Crypto Prices (`/tools/get_crypto_price`)
```bash
curl -X POST http://localhost:8080/tools/get_crypto_price \
  -H "Content-Type: application/json" \
  -d '{"coin_ids": ["bitcoin", "ethereum", "solana"], "vs_currency": "usd"}'
```
**Response:**
```json
{
  "result": "Cryptocurrency Prices (USD):\n- Bitcoin (bitcoin): $79,984.00 | 24h: +0.40% | 24h Vol: $20.19B | MCap: $1.61T\n- Ethereum (ethereum): $2,503.42 | 24h: +1.98% | 24h Vol: $8.73B | MCap: $305.40B\n- Solana (solana): $106.60 | 24h: +3.98% | 24h Vol: $2.41B | MCap: $49.80B",
  "error": null
}
```

### 2. Search Coins (`/tools/search_crypto_coins`)
```bash
curl -X POST http://localhost:8080/tools/search_crypto_coins \
  -H "Content-Type: application/json" \
  -d '{"query": "sol", "max_results": 3}'
```
**Response:**
```json
{
  "result": "Cryptocurrency search results for 'sol':\n1. Solana (SOL) - Rank #5 | ID: solana\n2. Solv Protocol (SOLV) - Rank #240 | ID: solv-protocol\n3. Solstice (SLX) - Unranked | ID: solstice",
  "error": null
}
```

### 3. Trending Cryptocurrencies (`/tools/get_trending_crypto`)
```bash
curl -X POST http://localhost:8080/tools/get_trending_crypto \
  -H "Content-Type: application/json" \
  -d '{"limit": 3}'
```

### 4. Market Overview (`/tools/get_crypto_market_overview`)
```bash
curl -X POST http://localhost:8080/tools/get_crypto_market_overview \
  -H "Content-Type: application/json" \
  -d '{"limit": 5, "vs_currency": "usd"}'
```

---

## Deployment

The app includes ready-to-use configuration for Railway:
- `railway.toml`: Automatic Nixpacks deployment with healthcheck configuration.
- `Procfile`: Standard Procfile for container and PaaS environments.
- `runtime.txt`: Pinned Python 3.11 runtime.
