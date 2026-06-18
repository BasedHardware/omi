"""
Harness self-tests.

These tests verify that the e2e harness guardrails fail closed before any
scenario depends on them.
"""

import os
import socket

import dotenv
import pytest


def test_dotenv_loading_is_disabled(tmp_path):
    """Local .env files must not rehydrate real credentials during e2e runs."""
    env_file = tmp_path / ".env"
    env_file.write_text("SERVICE_ACCOUNT_JSON=real-looking-secret\nPINECONE_API_KEY=real-looking-key\n")

    assert dotenv.load_dotenv(env_file, override=True) is False
    assert os.environ.get("SERVICE_ACCOUNT_JSON") is None
    assert os.environ.get("PINECONE_API_KEY") is None


def test_network_guard_blocks_external_dns_lookup():
    """External DNS resolution should fail before a client can connect."""
    with pytest.raises(AssertionError, match="blocked DNS lookup"):
        socket.getaddrinfo("example.com", 443)


def test_network_guard_blocks_external_create_connection():
    """External TCP connections should fail closed."""
    with pytest.raises(AssertionError, match="blocked outbound network connection"):
        socket.create_connection(("93.184.216.34", 80), timeout=0.1)


def test_network_guard_blocks_sendto_two_arg_form():
    """UDP sendto(data, address) should fail closed for non-local hosts."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(AssertionError, match="blocked outbound network connection"):
            sock.sendto(b"payload", ("93.184.216.34", 80))
    finally:
        sock.close()


def test_network_guard_blocks_sendto_three_arg_form():
    """UDP sendto(data, flags, address) should fail closed, not TypeError."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        with pytest.raises(AssertionError, match="blocked outbound network connection"):
            sock.sendto(b"payload", 0, ("93.184.216.34", 80))
    finally:
        sock.close()


def test_backend_storage_client_is_fake_after_app_import(client):
    """The backend storage module should hold the fake GCS client, not google's real client."""
    from fakes.storage import FakeStorageClient
    import utils.other.storage as storage_helpers

    assert isinstance(storage_helpers.storage_client, FakeStorageClient)
