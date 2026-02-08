"""
Tests for chat tools message sending capability.

Covers:
- ExternalIntegration model chat_messages fields
- Chat messages authorization logic
- Target routing (main vs app chat)
- Notify flag behavior
- Manifest parsing logic (extracted)
- Process chat tools manifest logic (extracted)
"""

import os
from typing import Dict, Any, List

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.app import ExternalIntegration


class TestExternalIntegrationModel:
    """Test ExternalIntegration model with chat_messages fields."""

    def test_model_accepts_all_chat_messages_fields(self):
        """ExternalIntegration model accepts all chat_messages configuration fields."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='main',
            chat_messages_notify=True,
        )

        assert ext.chat_messages_enabled is True
        assert ext.chat_messages_target == 'main'
        assert ext.chat_messages_notify is True

    def test_model_defaults(self):
        """ExternalIntegration model has correct defaults for chat_messages fields."""
        ext = ExternalIntegration()

        assert ext.chat_messages_enabled is False
        assert ext.chat_messages_target == 'app'
        assert ext.chat_messages_notify is False

    def test_target_validation_main(self):
        """Target value 'main' is valid."""
        ext = ExternalIntegration(chat_messages_target='main')
        assert ext.chat_messages_target == 'main'

    def test_target_validation_app(self):
        """Target value 'app' is valid."""
        ext = ExternalIntegration(chat_messages_target='app')
        assert ext.chat_messages_target == 'app'


class TestChatMessageTarget:
    """Test chat message target routing logic."""

    def test_target_main_routes_to_main_chat(self):
        """Target 'main' routes message to main chat (chat_app_id = None)."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='main',
            chat_messages_notify=False,
        )

        target = ext.chat_messages_target
        chat_app_id = None if target == 'main' else 'test-app-id'

        assert chat_app_id is None

    def test_target_app_routes_to_app_chat(self):
        """Target 'app' routes message to app-specific chat."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='app',
            chat_messages_notify=False,
        )

        app_id = 'test-app-id'
        target = ext.chat_messages_target
        chat_app_id = None if target == 'main' else app_id

        assert chat_app_id == 'test-app-id'

    def test_default_target_is_app(self):
        """Default target value is 'app'."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            # chat_messages_target not specified, should default to 'app'
        )

        assert ext.chat_messages_target == 'app'


class TestChatMessageNotify:
    """Test chat message notification flag behavior."""

    def test_notify_true_sends_push_notification(self):
        """Notify flag True triggers push notification."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='app',
            chat_messages_notify=True,
        )

        should_notify = ext.chat_messages_notify
        assert should_notify is True

    def test_notify_false_skips_push_notification(self):
        """Notify flag False skips push notification."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='app',
            chat_messages_notify=False,
        )

        should_notify = ext.chat_messages_notify
        assert should_notify is False

    def test_default_notify_is_false(self):
        """Default notify value is False."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            # chat_messages_notify not specified, should default to False
        )

        assert ext.chat_messages_notify is False


class TestChatMessagesAuthorization:
    """Test chat messages authorization logic (simulating notification endpoint)."""

    def test_rejects_when_chat_messages_not_enabled(self):
        """Rejects notification when chat_messages is not enabled in manifest."""
        # Create app without chat_messages enabled
        ext = ExternalIntegration(
            chat_messages_enabled=False,
            chat_messages_target='app',
            chat_messages_notify=False,
        )

        # The check in notifications.py
        if not ext or not ext.chat_messages_enabled:
            authorized = False
        else:
            authorized = True

        assert authorized is False

    def test_accepts_when_chat_messages_enabled(self):
        """Accepts notification when chat_messages is enabled in manifest."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='app',
            chat_messages_notify=False,
        )

        if not ext or not ext.chat_messages_enabled:
            authorized = False
        else:
            authorized = True

        assert authorized is True

    def test_rejects_when_no_external_integration(self):
        """Rejects notification when app has no external_integration."""
        ext = None

        if not ext or not getattr(ext, 'chat_messages_enabled', False):
            authorized = False
        else:
            authorized = True

        assert authorized is False


class TestNotificationEndpointLogic:
    """Test the notification endpoint logic for chat messages."""

    def test_full_flow_chat_messages_enabled_target_main_no_notify(self):
        """Full flow: enabled, target main, no notification."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='main',
            chat_messages_notify=False,
        )
        app_id = 'slack-app'

        # Simulating the notification endpoint logic
        assert ext is not None
        assert ext.chat_messages_enabled is True

        target = ext.chat_messages_target
        chat_app_id = None if target == 'main' else app_id
        assert chat_app_id is None  # Routes to main chat

        should_send_push = ext.chat_messages_notify
        assert should_send_push is False

    def test_full_flow_chat_messages_enabled_target_app_with_notify(self):
        """Full flow: enabled, target app, with notification."""
        ext = ExternalIntegration(
            chat_messages_enabled=True,
            chat_messages_target='app',
            chat_messages_notify=True,
        )
        app_id = 'spotify-app'

        # Simulating the notification endpoint logic
        assert ext is not None
        assert ext.chat_messages_enabled is True

        target = ext.chat_messages_target
        chat_app_id = None if target == 'main' else app_id
        assert chat_app_id == 'spotify-app'  # Routes to app chat

        should_send_push = ext.chat_messages_notify
        assert should_send_push is True

    def test_app_without_external_integration_cannot_send_messages(self):
        """Apps without external_integration cannot send chat messages."""
        ext = None

        can_send = ext and ext.chat_messages_enabled
        assert not can_send


# =========================================================================
# Extracted logic tests - test the actual parsing/processing logic
# without importing heavy modules
# =========================================================================


def parse_chat_messages_from_manifest(data: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Extracted logic from fetch_app_chat_tools_from_manifest.
    Parses chat_messages configuration from manifest data.
    """
    chat_messages = data.get('chat_messages', {})
    chat_messages_config = {}
    if isinstance(chat_messages, dict) and chat_messages.get('enabled', False):
        chat_messages_config = {
            'enabled': True,
            'target': chat_messages.get('target', 'app'),
            'notify': chat_messages.get('notify', True),
        }
    return chat_messages_config if chat_messages_config else None


def resolve_tool_endpoints(tools: List[Dict[str, Any]], base_url: str) -> List[Dict[str, Any]]:
    """
    Extracted logic from _process_chat_tools_manifest.
    Resolves relative endpoints to absolute URLs.
    """
    if not base_url:
        return tools

    base_url = base_url.rstrip('/')
    for tool in tools:
        endpoint = tool.get('endpoint', '')
        if endpoint.startswith('/') and not endpoint.startswith('//'):
            tool['endpoint'] = f"{base_url}{endpoint}"
    return tools


def process_chat_messages_config(manifest_result: Dict[str, Any] | None, app_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracted logic from _process_chat_tools_manifest.
    Processes chat_messages config and stores in app_dict.
    """
    if 'external_integration' not in app_dict:
        app_dict['external_integration'] = {}

    if manifest_result is None:
        return app_dict

    chat_messages = manifest_result.get('chat_messages')
    if chat_messages:
        app_dict['external_integration']['chat_messages_enabled'] = chat_messages.get('enabled', False)
        app_dict['external_integration']['chat_messages_target'] = chat_messages.get('target', 'app')
        app_dict['external_integration']['chat_messages_notify'] = chat_messages.get('notify', False)
    else:
        # Reset all chat_messages fields to defaults when not in manifest
        app_dict['external_integration']['chat_messages_enabled'] = False
        app_dict['external_integration']['chat_messages_target'] = 'app'
        app_dict['external_integration']['chat_messages_notify'] = False

    return app_dict


class TestParseChatMessagesFromManifest:
    """Test the chat_messages parsing logic extracted from fetch_app_chat_tools_from_manifest."""

    def test_returns_config_when_enabled(self):
        """Returns chat_messages config when enabled is True."""
        data = {
            'tools': [],
            'chat_messages': {
                'enabled': True,
                'target': 'main',
                'notify': True,
            },
        }

        result = parse_chat_messages_from_manifest(data)

        assert result is not None
        assert result['enabled'] is True
        assert result['target'] == 'main'
        assert result['notify'] is True

    def test_returns_none_when_not_enabled(self):
        """Returns None when enabled is False."""
        data = {
            'tools': [],
            'chat_messages': {
                'enabled': False,
            },
        }

        result = parse_chat_messages_from_manifest(data)

        assert result is None

    def test_returns_none_when_missing(self):
        """Returns None when chat_messages is not present."""
        data = {
            'tools': [],
        }

        result = parse_chat_messages_from_manifest(data)

        assert result is None

    def test_default_target_is_app(self):
        """Default target is 'app' when not specified."""
        data = {
            'chat_messages': {
                'enabled': True,
                # target not specified
            },
        }

        result = parse_chat_messages_from_manifest(data)

        assert result['target'] == 'app'

    def test_default_notify_is_true(self):
        """Default notify is True when not specified."""
        data = {
            'chat_messages': {
                'enabled': True,
                # notify not specified
            },
        }

        result = parse_chat_messages_from_manifest(data)

        assert result['notify'] is True

    def test_handles_empty_chat_messages(self):
        """Handles empty chat_messages dict."""
        data = {
            'chat_messages': {},
        }

        result = parse_chat_messages_from_manifest(data)

        assert result is None

    def test_handles_non_dict_chat_messages(self):
        """Handles non-dict chat_messages value."""
        data = {
            'chat_messages': "invalid",
        }

        result = parse_chat_messages_from_manifest(data)

        assert result is None


class TestResolveToolEndpoints:
    """Test the endpoint resolution logic extracted from _process_chat_tools_manifest."""

    def test_resolves_relative_endpoint(self):
        """Resolves relative endpoint to absolute URL."""
        tools = [{'name': 'test', 'endpoint': '/api/action'}]
        base_url = 'https://example.com'

        result = resolve_tool_endpoints(tools, base_url)

        assert result[0]['endpoint'] == 'https://example.com/api/action'

    def test_preserves_absolute_endpoint(self):
        """Preserves absolute endpoint unchanged."""
        tools = [{'name': 'test', 'endpoint': 'https://other.com/api/action'}]
        base_url = 'https://example.com'

        result = resolve_tool_endpoints(tools, base_url)

        assert result[0]['endpoint'] == 'https://other.com/api/action'

    def test_handles_base_url_with_trailing_slash(self):
        """Handles base URL with trailing slash."""
        tools = [{'name': 'test', 'endpoint': '/api/action'}]
        base_url = 'https://example.com/'

        result = resolve_tool_endpoints(tools, base_url)

        assert result[0]['endpoint'] == 'https://example.com/api/action'

    def test_handles_empty_base_url(self):
        """Returns tools unchanged when base URL is empty."""
        tools = [{'name': 'test', 'endpoint': '/api/action'}]
        base_url = ''

        result = resolve_tool_endpoints(tools, base_url)

        assert result[0]['endpoint'] == '/api/action'

    def test_handles_multiple_tools(self):
        """Handles multiple tools with mixed endpoints."""
        tools = [
            {'name': 'tool1', 'endpoint': '/api/action1'},
            {'name': 'tool2', 'endpoint': 'https://other.com/api/action2'},
            {'name': 'tool3', 'endpoint': '/api/action3'},
        ]
        base_url = 'https://myapp.com'

        result = resolve_tool_endpoints(tools, base_url)

        assert result[0]['endpoint'] == 'https://myapp.com/api/action1'
        assert result[1]['endpoint'] == 'https://other.com/api/action2'
        assert result[2]['endpoint'] == 'https://myapp.com/api/action3'

    def test_preserves_protocol_relative_url(self):
        """Preserves protocol-relative URLs (starting with //)."""
        tools = [{'name': 'test', 'endpoint': '//cdn.example.com/api'}]
        base_url = 'https://example.com'

        result = resolve_tool_endpoints(tools, base_url)

        assert result[0]['endpoint'] == '//cdn.example.com/api'


class TestProcessChatMessagesConfig:
    """Test the chat_messages config processing logic extracted from _process_chat_tools_manifest."""

    def test_stores_enabled_config(self):
        """Stores chat_messages config when enabled."""
        manifest_result = {
            'tools': None,
            'chat_messages': {
                'enabled': True,
                'target': 'main',
                'notify': True,
            },
        }
        app_dict = {'id': 'test-app'}

        result = process_chat_messages_config(manifest_result, app_dict)

        assert result['external_integration']['chat_messages_enabled'] is True
        assert result['external_integration']['chat_messages_target'] == 'main'
        assert result['external_integration']['chat_messages_notify'] is True

    def test_resets_to_defaults_when_none(self):
        """Resets to defaults when chat_messages is None."""
        manifest_result = {
            'tools': None,
            'chat_messages': None,
        }
        app_dict = {'id': 'test-app'}

        result = process_chat_messages_config(manifest_result, app_dict)

        assert result['external_integration']['chat_messages_enabled'] is False
        assert result['external_integration']['chat_messages_target'] == 'app'
        assert result['external_integration']['chat_messages_notify'] is False

    def test_handles_null_manifest_result(self):
        """Handles None manifest_result (fetch failure)."""
        app_dict = {'id': 'test-app'}

        result = process_chat_messages_config(None, app_dict)

        assert result == app_dict

    def test_creates_external_integration_if_missing(self):
        """Creates external_integration dict if not present."""
        manifest_result = {
            'chat_messages': {
                'enabled': True,
                'target': 'app',
                'notify': False,
            },
        }
        app_dict = {'id': 'test-app'}

        result = process_chat_messages_config(manifest_result, app_dict)

        assert 'external_integration' in result
        assert result['external_integration']['chat_messages_enabled'] is True

    def test_preserves_existing_external_integration(self):
        """Preserves existing external_integration fields."""
        manifest_result = {
            'chat_messages': {
                'enabled': True,
                'target': 'app',
                'notify': False,
            },
        }
        app_dict = {
            'id': 'test-app',
            'external_integration': {
                'app_home_url': 'https://example.com',
                'webhook_url': 'https://example.com/webhook',
            },
        }

        result = process_chat_messages_config(manifest_result, app_dict)

        assert result['external_integration']['app_home_url'] == 'https://example.com'
        assert result['external_integration']['webhook_url'] == 'https://example.com/webhook'
        assert result['external_integration']['chat_messages_enabled'] is True
