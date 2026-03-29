"""Tests for generative UI chat tools.

These tests intentionally load ``genui_tools.py`` in isolation so the tool logic can
be verified without requiring the full backend dependency graph.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def _load_genui_tools_module():
    """Load genui_tools.py with a minimal stub for the @tool decorator."""
    if "langchain_core" not in sys.modules:
        langchain_core = types.ModuleType("langchain_core")
        sys.modules["langchain_core"] = langchain_core
    else:
        langchain_core = sys.modules["langchain_core"]

    tools_mod = types.ModuleType("langchain_core.tools")

    def tool(fn):
        return fn

    tools_mod.tool = tool
    sys.modules["langchain_core.tools"] = tools_mod
    setattr(langchain_core, "tools", tools_mod)

    path = Path(__file__).resolve().parents[2] / "utils" / "retrieval" / "tools" / "genui_tools.py"
    spec = importlib.util.spec_from_file_location("test_genui_tools_module", path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_map_ui_stores_block_in_agent_config():
    module = _load_genui_tools_module()
    config = {"configurable": {}}
    token = module.agent_config_context.set(config)

    try:
        result = module.create_map_ui(latitude=40.7128, longitude=-74.0060, title="New York", description="NYC")
    finally:
        module.agent_config_context.reset(token)

    assert "Map displayed: New York" in result
    assert config["configurable"]["ui_blocks"] == [
        {
            "type": "map",
            "props": {
                "latitude": 40.7128,
                "longitude": -74.006,
                "title": "New York",
                "description": "NYC",
                "zoom": 15,
            },
        }
    ]


def test_create_map_ui_rejects_invalid_coordinates_without_storing_block():
    module = _load_genui_tools_module()
    config = {"configurable": {}}
    token = module.agent_config_context.set(config)

    try:
        result = module.create_map_ui(latitude=140.0, longitude=-74.0060, title="Bad")
    finally:
        module.agent_config_context.reset(token)

    assert result == "Error: latitude must be between -90 and 90."
    assert config["configurable"].get("ui_blocks") is None


def test_create_action_buttons_ui_limits_to_five_buttons():
    module = _load_genui_tools_module()
    config = {"configurable": {}}
    token = module.agent_config_context.set(config)

    try:
        result = module.create_action_buttons_ui(
            buttons=["One", "Two", "Three", "Four", "Five", "Six"],
            title="Quick actions",
        )
    finally:
        module.agent_config_context.reset(token)

    assert "Action buttons displayed" in result
    assert config["configurable"]["ui_blocks"] == [
        {
            "type": "action_buttons",
            "props": {
                "title": "Quick actions",
                "buttons": ["One", "Two", "Three", "Four", "Five"],
            },
        }
    ]
