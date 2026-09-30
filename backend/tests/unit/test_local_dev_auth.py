"""Contract for the local-development sign-in endpoint.

The endpoint exists because community builds cannot complete a real OAuth flow:
Google and Apple issue OAuth clients against the official bundle id, and a
community build is signed with a suffixed one. The risk it introduces is obvious
-- an endpoint that mints Firebase custom tokens with no provider check -- so the
gate is the part under test here, not the happy path.
"""

import importlib
from unittest import mock

import pytest


@pytest.fixture
def auth_module():
    return importlib.import_module("routers.auth")


class TestLocalDevAuthGate:
    def test_disabled_when_no_auth_emulator_is_configured(self, auth_module, monkeypatch):
        """Production has no FIREBASE_AUTH_EMULATOR_HOST, so the gate is shut."""
        monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
        assert auth_module.local_dev_auth_enabled() is False

    def test_disabled_when_the_variable_is_blank_or_whitespace(self, auth_module, monkeypatch):
        """An empty value must not read as 'configured'."""
        for value in ("", "   ", "\t"):
            monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", value)
            assert auth_module.local_dev_auth_enabled() is False, repr(value)

    def test_enabled_only_with_a_real_emulator_host(self, auth_module, monkeypatch):
        monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
        assert auth_module.local_dev_auth_enabled() is True

    @pytest.mark.asyncio
    async def test_returns_404_not_403_when_disabled(self, auth_module, monkeypatch):
        """404, not 403.

        A 403 confirms the route exists. On a production deployment this must be
        indistinguishable from a route that was never registered, so that the
        endpoint cannot be discovered by probing.
        """
        from fastapi import HTTPException

        monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
        with pytest.raises(HTTPException) as excinfo:
            await auth_module.local_dev_custom_token(uid="anyone")
        assert excinfo.value.status_code == 404

    @pytest.mark.asyncio
    async def test_disabled_gate_mints_nothing(self, auth_module, monkeypatch):
        """The gate must short-circuit before any token is created."""
        from fastapi import HTTPException

        monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST", raising=False)
        with mock.patch.object(auth_module.firebase_admin.auth, "create_custom_token") as mint:
            with pytest.raises(HTTPException):
                await auth_module.local_dev_custom_token(uid="anyone")
        mint.assert_not_called()


class TestLocalDevAuthBehaviour:
    @pytest.mark.asyncio
    async def test_mints_a_token_for_an_existing_emulator_user(self, auth_module, monkeypatch):
        monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")

        with mock.patch.object(auth_module.firebase_admin.auth, "get_user", return_value=object()), mock.patch.object(
            auth_module.firebase_admin.auth, "create_user"
        ) as create_user, mock.patch.object(
            auth_module.firebase_admin.auth, "create_custom_token", return_value=b"token-abc"
        ):
            result = await auth_module.local_dev_custom_token(uid="existing-user")

        assert result["custom_token"] == "token-abc"
        assert result["uid"] == "existing-user"
        assert result["provider"] == "local_dev"
        create_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_the_user_on_first_sign_in(self, auth_module, monkeypatch):
        """A legacy/unmigrated principal: a uid that does not exist yet must work.

        Without this the first sign-in on a fresh emulator would fail closed and
        the endpoint would be useless exactly when it is needed.
        """
        monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")

        with mock.patch.object(
            auth_module.firebase_admin.auth, "get_user", side_effect=Exception("not found")
        ), mock.patch.object(auth_module.firebase_admin.auth, "create_user") as create_user, mock.patch.object(
            auth_module.firebase_admin.auth, "create_custom_token", return_value=b"token-new"
        ):
            result = await auth_module.local_dev_custom_token(uid="brand-new-user")

        assert result["custom_token"] == "token-new"
        create_user.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_an_empty_uid(self, auth_module, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
        for bad in ("", "   "):
            with pytest.raises(HTTPException) as excinfo:
                await auth_module.local_dev_custom_token(uid=bad)
            assert excinfo.value.status_code == 400

    @pytest.mark.asyncio
    async def test_decodes_a_str_token_without_double_decoding(self, auth_module, monkeypatch):
        """create_custom_token returns bytes on some versions and str on others."""
        monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")

        with mock.patch.object(auth_module.firebase_admin.auth, "get_user", return_value=object()), mock.patch.object(
            auth_module.firebase_admin.auth, "create_custom_token", return_value="already-a-str"
        ):
            result = await auth_module.local_dev_custom_token(uid="u")

        assert result["custom_token"] == "already-a-str"
