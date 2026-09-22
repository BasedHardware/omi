# SEC EDGAR Omi App

Research public company profiles, recent filings, and annual XBRL facts from
Omi conversations.

This is a standalone read-only app backed by the official SEC EDGAR and XBRL
APIs. It requires no account, OAuth connection, API key, or Omi identity data.

## Tools

- `get_company_profile`: resolves a ticker, CIK, or company name and returns the
  SEC registrant profile.
- `list_recent_filings`: lists recent filings, optionally filtered to an exact
  form type such as `10-K`, `10-Q`, or `8-K`.
- `get_financial_snapshot`: returns up to five recent annual values for revenue,
  net income, assets, liabilities, stockholders' equity, cash and equivalents,
  and diluted EPS when those facts are present.

## SEC fair access

The SEC asks automated clients to identify themselves through the `User-Agent`
header. Set `SEC_USER_AGENT` to an app name followed by a real contact address
for production deployments:

```bash
export SEC_USER_AGENT="YourApp/1.0 contact@example.com"
```

The app uses a conservative public default when the variable is unset, performs
one submissions request plus at most one facts request per tool call, and maps
SEC `403` or `429` responses to a safe retry message.

Responses include a link to `sec.gov/edgar`. The app does not provide investment
advice and does not send Omi user identifiers to the SEC.

## Example requests

```bash
curl -X POST http://localhost:8080/tools/get_company_profile \
  -H "Content-Type: application/json" \
  -d '{"company":"AAPL"}'
```

```bash
curl -X POST http://localhost:8080/tools/list_recent_filings \
  -H "Content-Type: application/json" \
  -d '{"company":"Apple","form_type":"10-K","limit":3}'
```

```bash
curl -X POST http://localhost:8080/tools/get_financial_snapshot \
  -H "Content-Type: application/json" \
  -d '{"company":"MSFT","years":3}'
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Run the hermetic tests:

```bash
python test_main.py
```

Health check: `GET /health`

Tool manifest: `GET /.well-known/omi-tools.json`
