from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("github_client.py")
spec = importlib.util.spec_from_file_location("github_client", MODULE_PATH)
github_client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(github_client)


class FakeResponse:
    def __init__(self, payload, status_code=200, links=None):
        self._payload = payload
        self.status_code = status_code
        self.links = links or {}

    def json(self):
        return self._payload


def repo(name):
    return {
        "name": name,
        "full_name": f"owner/{name}",
        "owner": {"login": "owner"},
        "private": False,
        "description": f"{name} description",
        "html_url": f"https://github.com/owner/{name}",
    }


class GitHubClientTests(unittest.TestCase):
    def test_list_user_repos_follows_next_page(self):
        client = github_client.GitHubClient()

        with patch.object(
            github_client.requests,
            "get",
            side_effect=[
                FakeResponse([repo("one"), repo("two")], links={"next": {"url": "page-2"}}),
                FakeResponse([repo("three")]),
            ],
        ) as get:
            repos = client.list_user_repos("token", per_page=2)

        self.assertEqual([item["full_name"] for item in repos], ["owner/one", "owner/two", "owner/three"])
        self.assertEqual(get.call_count, 2)
        self.assertEqual(get.call_args_list[0].kwargs["params"], {"per_page": 2, "sort": "updated", "page": 1})
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"per_page": 2, "sort": "updated", "page": 2})

    def test_list_user_repos_returns_empty_on_api_error(self):
        client = github_client.GitHubClient()

        with patch.object(github_client.requests, "get", return_value=FakeResponse([], status_code=500)), patch.object(
            github_client, "print"
        ):
            self.assertEqual(client.list_user_repos("token"), [])

    def test_list_user_repos_accepts_empty_complete_page(self):
        client = github_client.GitHubClient()

        with patch.object(github_client.requests, "get", return_value=FakeResponse([])) as get:
            self.assertEqual(client.list_user_repos("token"), [])

        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"], {"per_page": 100, "sort": "updated", "page": 1})

    def test_list_user_repos_discards_partial_results_on_later_page_error(self):
        client = github_client.GitHubClient()

        with patch.object(
            github_client.requests,
            "get",
            side_effect=[
                FakeResponse([repo("one")], links={"next": {"url": "page-2"}}),
                FakeResponse([], status_code=500),
            ],
        ), patch.object(github_client, "print"):
            self.assertEqual(client.list_user_repos("token"), [])


if __name__ == "__main__":
    unittest.main()
