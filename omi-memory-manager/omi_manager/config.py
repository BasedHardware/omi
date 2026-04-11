"""Configuration management for Omi Memory Manager."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".omi-manager"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_BASE_URL = "https://api.omi.me"


def get_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_api_key() -> str:
    key = os.environ.get("OMI_API_KEY")
    if key:
        return key
    config = get_config()
    key = config.get("api_key")
    if not key:
        raise SystemExit(
            "API key not configured. Run: omi configure --api-key YOUR_KEY\n"
            "Or set the OMI_API_KEY environment variable.\n\n"
            "Get your key at: https://omi.me -> Settings -> Developer -> API Keys"
        )
    return key


def get_base_url() -> str:
    url = os.environ.get("OMI_BASE_URL")
    if url:
        return url
    config = get_config()
    return config.get("base_url", DEFAULT_BASE_URL)
