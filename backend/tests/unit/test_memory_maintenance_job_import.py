"""Regression coverage for the credential-free memory-maintenance image smoke."""

import ast
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
MODAL_DIR = BACKEND_DIR / "modal"
IMPORT_PURITY_SCANNER = BACKEND_DIR / "scripts" / "scan_import_time_side_effects.py"
PROVIDER_ENV_VARS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
SMOKE_ENCRYPTION_SECRET = "0123456789abcdef0123456789abcdef"


def _load_import_purity_scanner():
    spec = importlib.util.spec_from_file_location("import_purity_scanner_for_test", IMPORT_PURITY_SCANNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_purity_scanner_rejects_langchain_provider_constructors():
    scanner = _load_import_purity_scanner()
    source = "\n".join(
        (
            "from langchain_openai import ChatOpenAI, OpenAIEmbeddings",
            "chat = ChatOpenAI()",
            "embeddings = OpenAIEmbeddings()",
        )
    )

    offenders = scanner._module_level_offenders(ast.parse(source), source.splitlines())

    assert (2, "import-time constructor: ChatOpenAI") in offenders
    assert (3, "import-time constructor: OpenAIEmbeddings") in offenders


def test_memory_maintenance_job_imports_without_provider_credentials_or_network():
    environment = dict(os.environ)
    for variable in PROVIDER_ENV_VARS:
        environment.pop(variable, None)
    environment["ENCRYPTION_SECRET"] = SMOKE_ENCRYPTION_SECRET
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    code = f'''\
import socket
import sys
import types

class ForbiddenProviderClient:
    def __init__(self, *_args, **_kwargs):
        raise AssertionError("provider clients must not be constructed while importing the job")

class BlockedNetworkSocket(socket.socket):
    def connect(self, *_args, **_kwargs):
        raise AssertionError("network access is forbidden while importing the job")

socket.socket = BlockedNetworkSocket
anthropic = types.ModuleType("anthropic")
anthropic.AsyncAnthropic = ForbiddenProviderClient
langchain_openai = types.ModuleType("langchain_openai")
langchain_openai.ChatOpenAI = ForbiddenProviderClient
langchain_openai.OpenAIEmbeddings = ForbiddenProviderClient
tiktoken = types.ModuleType("tiktoken")
tiktoken.encoding_for_model = lambda *_args, **_kwargs: (_ for _ in ()).throw(
    AssertionError("tokenizer must not initialize while importing the job")
)
sys.modules.update({{
    "anthropic": anthropic,
    "langchain_openai": langchain_openai,
    "tiktoken": tiktoken,
}})
sys.path.insert(0, {str(BACKEND_DIR)!r})
sys.path.insert(0, {str(MODAL_DIR)!r})
import memory_maintenance_job
'''

    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code],
        cwd=BACKEND_DIR,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
