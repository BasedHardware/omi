"""Tests for the rayban_meta conversation source.

Ray-Ban Meta glasses stream with source=rayban_meta on /v4/listen and reuse
the OpenGlass image_chunk pipeline for photos. These tests pin the two
contracts that make that work: the enum member exists (otherwise
ConversationSource._missing_ silently degrades it to 'unknown'), and storing
photos must not overwrite the rayban_meta provenance with 'openglass'.
"""

import sys
from unittest.mock import MagicMock

# Stub heavy dependencies before importing models
for mod in [
    'firebase_admin',
    'firebase_admin.firestore',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'google.cloud.firestore',
    'google.auth.transport.requests',
    'google.oauth2.id_token',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.base_query',
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from models.conversation_enums import ConversationSource
from utils.transcribe_decisions import PHOTO_CAPABLE_SOURCE_VALUES, resolve_photo_conversation_source


class TestRayBanMetaSourceEnum:
    def test_rayban_meta_is_known_member(self):
        result = ConversationSource('rayban_meta')
        assert result == ConversationSource.rayban_meta
        assert result.value == 'rayban_meta'

    def test_rayban_meta_does_not_degrade_to_unknown(self):
        assert ConversationSource('rayban_meta') != ConversationSource.unknown

    def test_conversation_model_accepts_rayban_meta(self):
        from models.conversation import Conversation
        from models.structured import Structured

        conv = Conversation(
            id='test-rbm-1',
            created_at='2026-07-06T18:00:00Z',
            started_at='2026-07-06T18:00:00Z',
            finished_at='2026-07-06T18:15:00Z',
            source='rayban_meta',
            structured=Structured(title='Test', overview='Test overview', emoji='🕶️'),
        )
        assert conv.source == ConversationSource.rayban_meta


class TestResolvePhotoConversationSource:
    """Contract for the photo → source relabeling in transcribe.py."""

    def test_openglass_source_is_preserved(self):
        assert resolve_photo_conversation_source('openglass') is None

    def test_rayban_meta_source_is_preserved(self):
        assert resolve_photo_conversation_source('rayban_meta') is None

    def test_legacy_sources_flip_to_openglass(self):
        # Devices without native photo support keep the historical behavior:
        # a photo-bearing conversation gets the openglass label.
        for source in ('omi', 'friend', 'phone', 'apple_watch', None):
            assert resolve_photo_conversation_source(source) == 'openglass'

    def test_photo_capable_values_are_valid_enum_members(self):
        for value in PHOTO_CAPABLE_SOURCE_VALUES:
            assert ConversationSource(value).value == value
