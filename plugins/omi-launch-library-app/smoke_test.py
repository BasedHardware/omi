"""Optional live smoke checks against the public Launch Library 2 API."""

from fastapi.testclient import TestClient

from main import app


def main() -> None:
    with TestClient(app) as client:
        upcoming = client.post(
            "/tools/get_upcoming_launches",
            json={"days": 90, "limit": 2},
        )
        upcoming.raise_for_status()
        payload = upcoming.json()
        assert payload["error"] is None, payload
        assert "upcoming launches" in payload["result"], payload
        print("get_upcoming_launches: ok")

        search = client.post(
            "/tools/search_launches",
            json={"query": "Falcon 9", "limit": 2},
        )
        search.raise_for_status()
        payload = search.json()
        assert payload["error"] is None, payload
        assert "matching launches" in payload["result"], payload
        print("search_launches: ok")

        detail = client.post(
            "/tools/get_launch",
            json={"launch_id": "5af31461-bce5-4cfb-a0ee-b527cf285d90"},
        )
        detail.raise_for_status()
        payload = detail.json()
        assert payload["error"] is None, payload
        assert "Launch Library ID" in payload["result"], payload
        print("get_launch: ok")


if __name__ == "__main__":
    main()
