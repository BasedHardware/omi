"""Stdlib-only dependency doubles for the Whoop handler regression suites."""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import Mock, patch


class DummyFastAPI:
    def __init__(self, **_kwargs):
        pass

    def get(self, _path, **_kwargs):
        return lambda handler: handler

    post = get


class DummyBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class DummyRequest:
    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload


def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_main():
    """Load real handlers/models with isolated, fail-fast I/O doubles.

    Restore sys.modules after import so discovery cannot leak these dependency
    doubles into other suites, or reuse another plugin's generic main/models/db.
    """
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = DummyRequest
    fastapi.Query = lambda default=None, **_kwargs: default
    fastapi.HTTPException = Exception

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = object
    responses.RedirectResponse = object
    responses.JSONResponse = object

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    requests = types.ModuleType("requests")
    requests.get = Mock(side_effect=AssertionError("Unexpected Whoop HTTP GET"))
    requests.post = Mock(side_effect=AssertionError("Unexpected Whoop HTTP POST"))

    db = types.ModuleType("db")
    for name in (
        "store_whoop_tokens",
        "get_whoop_tokens",
        "update_whoop_tokens",
        "delete_whoop_tokens",
        "store_oauth_state",
        "get_uid_from_oauth_state",
        "delete_oauth_state",
        "store_user_setting",
        "get_user_setting",
    ):
        setattr(db, name, Mock(side_effect=AssertionError(f"Unexpected storage call: {name}")))

    modules = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "pydantic": pydantic,
        "dotenv": dotenv,
        "requests": requests,
        "db": db,
    }
    with patch.dict(sys.modules, modules):
        models = _load_module("whoop_models_under_test", "models.py")
        with patch.dict(sys.modules, {"models": models}):
            return _load_module("whoop_main_under_test", "main.py")
