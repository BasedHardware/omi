"""Tests for explicit stdin input on ``omi memory create --stdin`` / ``update --content-stdin``."""

from __future__ import annotations

import json
import types

import pytest

from omi_cli.main import app

_MEMORY = {"id": "m1", "content": "x", "category": "core", "visibility": "private", "tags": []}


# --- memory create --stdin ---------------------------------------------------


def test_create_stdin_posts_piped_content(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--stdin"], input="likes green tea\n")
    assert result.exit_code == 0, result.stderr
    body = json.loads(route.calls.last.request.content)
    assert body["content"] == "likes green tea"  # one trailing newline dropped
    assert body["visibility"] == "private"


def test_create_stdin_preserves_multiline_and_unicode(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    text = "line one\n  line two — naïve café 日本語 🙂\n"
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--stdin"], input=text)
    assert result.exit_code == 0, result.stderr
    body = json.loads(route.calls.last.request.content)
    assert body["content"] == "line one\n  line two — naïve café 日本語 🙂"


def test_create_stdin_strips_only_one_trailing_newline(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--stdin"], input="a\n\n")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content)["content"] == "a\n"


def test_create_stdin_keeps_other_options(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(
        app,
        ["--json", "memory", "create", "--stdin", "--category", "work", "--visibility", "public", "--tag", "a"],
        input="from a pipe",
    )
    assert result.exit_code == 0, result.stderr
    body = json.loads(route.calls.last.request.content)
    assert body == {"content": "from a pipe", "visibility": "public", "tags": ["a"], "category": "work"}


@pytest.mark.parametrize("piped", ["", "\n", "   \n\t \n"])
def test_create_stdin_rejects_empty_without_request(authed_profile, respx_mock, cli_runner, piped) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "create", "--stdin"], input=piped)
    assert result.exit_code == 1
    assert "no memory content on stdin" in result.stderr.lower()
    assert route.call_count == 0


def test_create_stdin_rejects_oversize_without_request(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "create", "--stdin"], input="é" * 501)
    assert result.exit_code == 1
    assert "1-500 characters" in result.stderr
    assert route.call_count == 0


def test_create_stdin_accepts_exactly_500_chars(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--stdin"], input="é" * 500 + "\n")
    assert result.exit_code == 0, result.stderr
    assert len(json.loads(route.calls.last.request.content)["content"]) == 500


def test_create_rejects_argument_and_stdin_together(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "create", "from arg", "--stdin"], input="from pipe")
    assert result.exit_code == 1
    assert "conflicting content sources" in result.stderr.lower()
    assert route.call_count == 0


def test_create_without_content_or_stdin_is_usage_error(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "create"], input="ignored because --stdin was not passed")
    assert result.exit_code == 1
    assert "no memory content" in result.stderr.lower()
    assert route.call_count == 0


def test_create_stdin_refuses_a_terminal(authed_profile, respx_mock, cli_runner, monkeypatch) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)

    class _Tty:
        def isatty(self) -> bool:
            return True

        def read(self) -> str:  # pragma: no cover - must never be called
            raise AssertionError("stdin read from a terminal")

    # CliRunner swaps sys.stdin during invoke, so patch the module's view of sys instead.
    monkeypatch.setattr("omi_cli.commands.memory.sys", types.SimpleNamespace(stdin=_Tty()))
    result = cli_runner.invoke(app, ["memory", "create", "--stdin"])
    assert result.exit_code == 1
    assert "needs piped input" in result.stderr.lower()
    assert route.call_count == 0


def test_create_argument_form_unchanged(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "plain arg"], input="must not be read")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content)["content"] == "plain arg"


# --- memory update --content-stdin -------------------------------------------


def test_update_content_stdin_patches_piped_content(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--content-stdin"], input="new\nvalue\n")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"content": "new\nvalue"}


def test_update_content_stdin_with_other_fields(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(
        app, ["--json", "memory", "update", "m1", "--content-stdin", "--visibility", "public"], input="v"
    )
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"content": "v", "visibility": "public"}


def test_update_rejects_content_and_content_stdin(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "update", "m1", "--content", "a", "--content-stdin"], input="b")
    assert result.exit_code == 1
    assert "conflicting content sources" in result.stderr.lower()
    assert route.call_count == 0


@pytest.mark.parametrize("piped", ["", "x" * 501])
def test_update_content_stdin_validates_before_request(authed_profile, respx_mock, cli_runner, piped) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "update", "m1", "--content-stdin"], input=piped)
    assert result.exit_code == 1
    assert route.call_count == 0


def test_update_content_option_unchanged(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--content", "c"], input="must not be read")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"content": "c"}


# --- edge cases ---------------------------------------------------------------


def test_create_stdin_preserves_leading_and_trailing_spaces(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--stdin"], input="  padded  \n")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content)["content"] == "  padded  "


@pytest.mark.parametrize(
    ("text", "ok"),
    [
        ("🙂" * 500, True),  # astral code points count once each
        ("🙂" * 501, False),
        ("é" * 250, True),  # combining marks count as code points (500)
        ("é" * 251, False),
        ("a" * 500 + "\n", True),  # the stripped newline is not content
        ("a" * 500 + "\n\n", False),  # second newline is content -> 501
    ],
)
def test_create_stdin_limit_counts_code_points(authed_profile, respx_mock, cli_runner, text, ok) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--stdin"], input=text)
    assert (result.exit_code == 0) is ok, result.stderr
    assert route.call_count == (1 if ok else 0)


def test_create_stdin_rejects_invalid_utf8_without_request(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["memory", "create", "--stdin"], input=b"ok \xff\xfe bad")
    assert result.exit_code == 1
    assert "utf-8" in result.stderr.lower()
    assert route.call_count == 0


def test_create_dash_argument_stays_literal(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "create", "--", "-"], input="must not be read")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content)["content"] == "-"


def test_update_dash_content_stays_literal(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--content", "-"], input="not read")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"content": "-"}


def test_update_content_stdin_with_category_visibility_and_tags(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(
        app,
        ["--json", "memory", "update", "m1", "--content-stdin", "--category", "work", "--visibility", "public",
         "--tag", "a", "--tag", "b"],
        input="n\n",
    )  # fmt: skip
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {
        "content": "n",
        "category": "work",
        "visibility": "public",
        "tags": ["a", "b"],
    }


def test_update_content_stdin_refuses_a_terminal(authed_profile, respx_mock, cli_runner, monkeypatch) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)

    class _Tty:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr("omi_cli.commands.memory.sys", types.SimpleNamespace(stdin=_Tty()))
    result = cli_runner.invoke(app, ["memory", "update", "m1", "--content-stdin"])
    assert result.exit_code == 1
    assert "needs piped input" in result.stderr.lower()
    assert route.call_count == 0


def test_update_stdin_not_read_when_other_field_given(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json=_MEMORY)
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--visibility", "public"], input="unread")
    assert result.exit_code == 0, result.stderr
    assert json.loads(route.calls.last.request.content) == {"visibility": "public"}
