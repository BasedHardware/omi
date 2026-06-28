# Public Holidays Omi App

Look up public holidays, upcoming holidays, long weekends, and supported countries from Omi conversations.

This is a standalone no-auth Omi app backed by the public Nager.Date API. It does not require environment variables, OAuth, or API keys.

## Tools

- `get_public_holidays`: list public holidays for a country and year.
- `get_next_public_holidays`: list upcoming public holidays for a country.
- `get_long_weekends`: list long weekends and bridge days for a country and year.
- `list_supported_countries`: list country codes supported by the API.

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

Example holiday request:

```bash
curl -X POST http://localhost:8080/tools/get_public_holidays \
  -H "Content-Type: application/json" \
  -d '{"country_code":"US","year":2026,"limit":8}'
```

Example long-weekend request:

```bash
curl -X POST http://localhost:8080/tools/get_long_weekends \
  -H "Content-Type: application/json" \
  -d '{"country_code":"US","year":2025}'
```

## Notes

- Country codes use ISO 3166-1 alpha-2 codes such as `US`, `DE`, or `JP`.
- Some holidays are regional; output marks whether a holiday is global and includes county codes when present.
- Long-weekend coverage depends on the upstream API data for each country and year.
