/// One chat session — a thread of messages the user can name, pin, or delete.
///
/// Mirrors desktop-v2's `ChatSession` interface (id/title/createdAt/
/// updatedAt/preview/messageCount) plus a `pinned` flag added in v0 per the
/// CEO review (lets users surface their main thread above date buckets).
///
/// Sessions persist in `chat.sessions.v1`. Messages persist separately in
/// `chat.messages.v1` and reference their session via `ChatMessage.sessionId`.
class ChatSession {
  ChatSession({
    required this.id,
    required this.title,
    required this.createdAt,
    required this.updatedAt,
    this.preview,
    this.messageCount = 0,
    this.pinned = false,
  });

  final String id;
  final String title;
  final DateTime createdAt;
  final DateTime updatedAt;

  /// Short preview taken from the first user message in the session. Optional
  /// because new sessions before the first send have no preview.
  final String? preview;

  /// Cached count of messages in this session. Provider keeps it in sync.
  final int messageCount;

  /// Pinned sessions render in a dedicated "PINNED" section above the date
  /// buckets and stay there regardless of `updatedAt`. CEO expansion #2.
  final bool pinned;

  ChatSession copyWith({
    String? title,
    DateTime? updatedAt,
    String? preview,
    int? messageCount,
    bool? pinned,
  }) =>
      ChatSession(
        id: id,
        title: title ?? this.title,
        createdAt: createdAt,
        updatedAt: updatedAt ?? this.updatedAt,
        preview: preview ?? this.preview,
        messageCount: messageCount ?? this.messageCount,
        pinned: pinned ?? this.pinned,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'createdAt': createdAt.toIso8601String(),
        'updatedAt': updatedAt.toIso8601String(),
        if (preview != null) 'preview': preview,
        'messageCount': messageCount,
        if (pinned) 'pinned': true,
      };

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    return ChatSession(
      id: json['id'] as String,
      title: (json['title'] as String?)?.trim().isNotEmpty == true
          ? json['title'] as String
          : 'New chat',
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
      preview: json['preview'] as String?,
      messageCount: json['messageCount'] as int? ?? 0,
      pinned: json['pinned'] as bool? ?? false,
    );
  }
}

/// First-message → session-title derivation. Trims, collapses whitespace,
/// caps at 40 chars with ellipsis. Falls back to "New chat" on empty input.
/// Called once on the first user message landing in a fresh session
/// (one-shot per [ChatProvider.send]).
String deriveSessionTitle(String firstUserMessage) {
  final cleaned = firstUserMessage.trim().replaceAll(RegExp(r'\s+'), ' ');
  if (cleaned.isEmpty) return 'New chat';
  if (cleaned.length <= 40) return cleaned;
  return '${cleaned.substring(0, 40).trimRight()}…';
}
