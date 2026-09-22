"""Optional live smoke checks against the official SEC EDGAR APIs."""

import os
import time

from fastapi.testclient import TestClient

from main import DEFAULT_USER_AGENT, app


def main() -> None:
    os.environ.setdefault("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    with TestClient(app) as client:
        profile = client.post(
            "/tools/get_company_profile",
            json={"company": "0000320193"},
        )
        profile.raise_for_status()
        payload = profile.json()
        assert payload["error"] is None, payload
        assert "Apple Inc." in payload["result"], payload
        print("get_company_profile: ok")
        time.sleep(0.2)

        filings = client.post(
            "/tools/list_recent_filings",
            json={"company": "0000320193", "form_type": "10-K", "limit": 2},
        )
        filings.raise_for_status()
        payload = filings.json()
        assert payload["error"] is None, payload
        assert "Recent SEC filings" in payload["result"], payload
        print("list_recent_filings: ok")
        time.sleep(0.2)

        facts = client.post(
            "/tools/get_financial_snapshot",
            json={"company": "0000320193", "years": 2},
        )
        facts.raise_for_status()
        payload = facts.json()
        assert payload["error"] is None, payload
        assert "Financial snapshot" in payload["result"], payload
        print("get_financial_snapshot: ok")


if __name__ == "__main__":
    main()
