/// One message in the chat tab thread.
///
/// `streaming` is set on the assistant message while we're still receiving
/// chunks from the backend. On rehydrate from Hive we drop streaming-true
/// rows — they represent an interrupted fetch (hot restart mid-stream) and
/// resuming partial responses isn't worth the complexity.
///
/// `toolEvents` accumulates labels for any tool the agent invoked while
/// producing this assistant message (e.g. "Searched memory", "Created
/// event"). Rendered as quiet chip lines above the bubble text so the user
/// sees what the assistant looked at before answering.
///
/// `sessionId` partitions messages across chat sessions. Nullable on disk
/// only for pre-migration messages — the provider's hydrate detects nulls
/// and assigns them to the "Welcome chat" session, then no message has a
/// null sessionId in memory after migration.
class ChatMessage {
  ChatMessage({
    required this.id,
    required this.role,
    required this.text,
    required this.createdAt,
    this.streaming = false,
    this.toolEvents = const [],
    this.sessionId,
    this.stopped = false,
  });

  final String id;
  final ChatRole role;
  final String text;
  final DateTime createdAt;
  final bool streaming;
  final List<String> toolEvents;
  final String? sessionId;

  /// True when the user pressed "Stop generating" mid-stream. Renderer shows
  /// a "⏹ Stopped" inline marker after the partial text. CEO expansion #1.
  final bool stopped;

  ChatMessage copyWith({
    String? text,
    bool? streaming,
    List<String>? toolEvents,
    String? sessionId,
    bool? stopped,
  }) =>
      ChatMessage(
        id: id,
        role: role,
        text: text ?? this.text,
        createdAt: createdAt,
        streaming: streaming ?? this.streaming,
        toolEvents: toolEvents ?? this.toolEvents,
        sessionId: sessionId ?? this.sessionId,
        stopped: stopped ?? this.stopped,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role.name,
        'text': text,
        'createdAt': createdAt.toIso8601String(),
        if (streaming) 'streaming': true,
        if (toolEvents.isNotEmpty) 'toolEvents': toolEvents,
        if (sessionId != null) 'sessionId': sessionId,
        if (stopped) 'stopped': true,
      };

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    final raw = json['toolEvents'];
    final events = raw is List
        ? raw.map((e) => e.toString()).toList(growable: false)
        : const <String>[];
    return ChatMessage(
      id: json['id'] as String,
      role: ChatRole.values.firstWhere(
        (r) => r.name == json['role'] as String?,
        orElse: () => ChatRole.assistant,
      ),
      text: json['text'] as String? ?? '',
      createdAt: DateTime.parse(json['createdAt'] as String),
      streaming: json['streaming'] as bool? ?? false,
      toolEvents: events,
      sessionId: json['sessionId'] as String?,
      stopped: json['stopped'] as bool? ?? false,
    );
  }
}

enum ChatRole { user, assistant }
