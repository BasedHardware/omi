"""Optional live smoke checks. Not registered in CI because it uses the network."""

from fastapi.testclient import TestClient

from main import app


def main() -> None:
    with TestClient(app) as client:
        search = client.post(
            "/tools/search_clinical_trials",
            json={
                "condition": "type 2 diabetes",
                "location": "Boston",
                "phase": "PHASE2",
                "page_size": 2,
            },
        )
        search.raise_for_status()
        payload = search.json()
        assert payload["error"] is None, payload
        assert "NCT" in payload["result"], payload
        print("search_clinical_trials: ok")

        recruiting = client.post(
            "/tools/find_recruiting_trials",
            json={"condition": "asthma", "page_size": 2},
        )
        recruiting.raise_for_status()
        payload = recruiting.json()
        assert payload["error"] is None, payload
        assert "Status: Recruiting" in payload["result"], payload
        print("find_recruiting_trials: ok")

        details = client.post(
            "/tools/get_clinical_trial", json={"nct_id": "NCT04280705"}
        )
        details.raise_for_status()
        payload = details.json()
        assert payload["error"] is None, payload
        assert "NCT04280705" in payload["result"], payload
        print("get_clinical_trial: ok")


if __name__ == "__main__":
    main()
