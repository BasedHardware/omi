"""Phase 5.2 contract test: the inventory's raw-decode count must survive
regex-whitelist removal.

This test asserts that WIRE_DECODE_RE does NOT contain hardcoded class-name
whitelists (e.g. ``ServerConversation.fromJson``) that dishonestly mark
hand-written decoders as "generated-backed". If someone re-adds a whitelist to
make the gate green by exception, this test fails.

The fix (Phase 5.1) removed these whitelists so the inventory reports the true
raw count. Phase 4 (client-code deletion) is what brings that count to 0 — not
whitelist patches.
"""

import re

from scripts.inventory_app_client_schemas import WIRE_DECODE_RE

# Hand-written fromJson methods (NOT fromGeneratedWireJson — that IS generated-backed).
# None of these should match WIRE_DECODE_RE — they are hand-written decoders.
HAND_WRITTEN_PATTERNS = [
    'ServerConversation.fromJson({})',
    'ServerMessage.fromResponseJson({})',
    'AgentVmInfo.fromJson({})',
    'AgentVmInfo.fromJsonBody({})',
    'TranscriptSegment.fromJson({})',
]

# Legitimate generated-backed patterns that SHOULD match.
GENERATED_BACKED_PATTERNS = [
    'wire.GeneratedActionItemResponse.fromJson({})',
    'actionItem.fromGenerated(generated)',
    'Conversation.fromGeneratedWireJson(json)',
]


class TestWireDecodeRegexHonesty:
    def test_hand_written_decoders_not_whitelisted(self):
        """No hand-written class-name whitelist should survive in WIRE_DECODE_RE."""
        for pattern in HAND_WRITTEN_PATTERNS:
            assert not WIRE_DECODE_RE.search(pattern), (
                f'WIRE_DECODE_RE incorrectly matches hand-written pattern: {pattern!r}. '
                f'This is a regex whitelist — remove it from the regex; fix the underlying '
                f'raw decode site instead (Phase 4 deletion).'
            )

    def test_generated_backed_patterns_still_match(self):
        """Legitimate generated-backed decode patterns must still match."""
        for pattern in GENERATED_BACKED_PATTERNS:
            assert WIRE_DECODE_RE.search(pattern), f'WIRE_DECODE_RE should match generated-backed pattern: {pattern!r}'

    def test_regex_has_no_hardcoded_class_names(self):
        """The regex source must not contain specific Dart class names."""
        source = WIRE_DECODE_RE.pattern
        # These are the class names that were previously whitelisted.
        forbidden_names = [
            'ServerConversation',
            'ServerMessage',
            'AgentVmInfo',
            'TranscriptSegment',
            'TranscriptsResponse',
            'CreateConversationResponse',
        ]
        for name in forbidden_names:
            assert name not in source, (
                f'WIRE_DECODE_RE contains hardcoded class name {name!r} — '
                f'this is a whitelist. Use generic patterns only.'
            )
