"""List IDs must not be truncated (#13039)."""


def test_list_ids_are_not_truncated(authed_profile, respx_mock, cli_runner):
    from omi_cli.main import app

    full_id = "12345678-1234-4234-8234-123456789abc"
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": full_id, "content": "hello world", "category": "note", "tags": []}]
    )
    result = cli_runner.invoke(app, ["memory", "list"])
    assert result.exit_code == 0
    assert full_id in result.stdout
    assert "12345678-1234\u2026" not in result.stdout
