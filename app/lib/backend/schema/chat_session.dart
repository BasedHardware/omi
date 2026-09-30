// A server-owned chat thread. This is a list projection, not a second transcript store.
//
// Decoding delegates to the generated app-client wire DTO
// (`wire.GeneratedChatSessionResponse`, from
// `docs/api-reference/app-client-openapi.json` via
// `backend/scripts/generate_dart_models.py`), which is the single source of truth for
// the `POST/GET/PATCH /v2/chat-sessions` response shape. `_normalizeWireJson` only fills
// fields a partial producer omits (the desktop Rust projection and older list projections
// send `updated_at` without `created_at`, `message_count`, or `starred`).

import 'package:omi/backend/schema/gen/chat_sessions_wire.g.dart' as wire;

/// A server-owned chat thread. This is a list projection, not a second transcript store.
class ChatSessionSummary {
  const ChatSessionSummary(
      {required this.id, required this.title, required this.updatedAt, this.preview = '', this.messageCount = 0});

  final String id;
  final String title;
  final String preview;
  final DateTime updatedAt;
  final int messageCount;

  bool get hasTitle => title.trim().isNotEmpty && title.trim() != 'New Chat';
  bool get hasContent => messageCount > 0 || hasTitle || preview.trim().isNotEmpty;

  factory ChatSessionSummary.fromJson(Map<String, dynamic> json) {
    // The wire decoder owns typing, nullability, and required-field enforcement.
    return ChatSessionSummary.fromGenerated(wire.GeneratedChatSessionResponse.fromJson(_normalizeWireJson(json)));
  }

  factory ChatSessionSummary.fromGenerated(wire.GeneratedChatSessionResponse generated) {
    if (generated.id.isEmpty) throw const FormatException('Invalid chat session');
    return ChatSessionSummary(
      id: generated.id,
      title: generated.title,
      preview: generated.preview ?? '',
      updatedAt: generated.updatedAt,
      messageCount: generated.messageCount,
    );
  }

  static Map<String, dynamic> _normalizeWireJson(Map<String, dynamic> json) {
    final normalized = Map<String, dynamic>.of(json);
    final date = normalized['updated_at'] ?? normalized['created_at'];
    normalized['updated_at'] ??= date;
    normalized['created_at'] ??= date;
    normalized['title'] ??= '';
    normalized['preview'] ??= '';
    normalized['message_count'] ??= 0;
    normalized['starred'] ??= false;
    return normalized;
  }
}
