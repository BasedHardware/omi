# Frankfurter Currency Omi App

Convert currencies and check reference exchange rates from Omi conversations.

This is a standalone no-auth Omi app backed by the public Frankfurter API. It does not require environment variables, OAuth, or API keys.

## Tools

- `convert_currency`: convert an amount from one currency into one or more target currencies.
- `get_latest_rates`: fetch latest reference rates for a base currency.
- `list_supported_currencies`: list currencies supported by the Frankfurter API.

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

Example conversion:

```bash
curl -X POST http://localhost:8080/tools/convert_currency \
  -H "Content-Type: application/json" \
  -d '{"amount":50,"from_currency":"USD","to_currencies":["EUR","CNY"]}'
```

Example latest rates:

```bash
curl -X POST http://localhost:8080/tools/get_latest_rates \
  -H "Content-Type: application/json" \
  -d '{"base_currency":"USD","to_currencies":["EUR","GBP","JPY"]}'
```

## Notes

- Frankfurter provides reference exchange rates, not trading quotes.
- Unsupported currencies return a clear error from the API.
- Results include the source date returned by Frankfurter.
