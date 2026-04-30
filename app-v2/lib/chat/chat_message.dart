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
class ChatMessage {
  ChatMessage({
    required this.id,
    required this.role,
    required this.text,
    required this.createdAt,
    this.streaming = false,
    this.toolEvents = const [],
  });

  final String id;
  final ChatRole role;
  final String text;
  final DateTime createdAt;
  final bool streaming;
  final List<String> toolEvents;

  ChatMessage copyWith({
    String? text,
    bool? streaming,
    List<String>? toolEvents,
  }) =>
      ChatMessage(
        id: id,
        role: role,
        text: text ?? this.text,
        createdAt: createdAt,
        streaming: streaming ?? this.streaming,
        toolEvents: toolEvents ?? this.toolEvents,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role.name,
        'text': text,
        'createdAt': createdAt.toIso8601String(),
        if (streaming) 'streaming': true,
        if (toolEvents.isNotEmpty) 'toolEvents': toolEvents,
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
    );
  }
}

enum ChatRole { user, assistant }
