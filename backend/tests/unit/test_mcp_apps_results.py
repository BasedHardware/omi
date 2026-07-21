"""Tests that SimpleConversation includes apps_results field."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from routers.mcp import SimpleConversation, SimpleStructured
from models.conversation_enums import CategoryEnum
from models.conversation import AppResult


def test_simple_conversation_includes_apps_results():
    """SimpleConversation should include apps_results field."""
    conv = SimpleConversation(
        id="test-id",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        structured=SimpleStructured(
            title="Test",
            overview="Test overview",
            category=CategoryEnum.personal,
        ),
        apps_results=[AppResult(app_id="app-1", content="Custom summary")],
    )
    assert len(conv.apps_results) == 1
    assert conv.apps_results[0].content == "Custom summary"
    assert conv.apps_results[0].app_id == "app-1"


def test_simple_conversation_apps_results_defaults_to_empty():
    """apps_results should default to empty list."""
    conv = SimpleConversation(
        id="test-id",
        started_at=datetime.now(),
        finished_at=datetime.now(),
        structured=SimpleStructured(
            title="Test",
            overview="Test overview",
            category=CategoryEnum.personal,
        ),
    )
    assert conv.apps_results == []
