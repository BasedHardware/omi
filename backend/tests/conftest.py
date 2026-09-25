"""
Optional: Provide a pytest fixture for the FastAPI test client if the project
does not already expose one. This file ensures that the test suite can import
the ``client`` fixture without duplication.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app  # adjust if the app is defined elsewhere


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
