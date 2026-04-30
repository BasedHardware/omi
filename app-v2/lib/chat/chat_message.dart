/// One message in the chat tab thread.
///
/// `streaming` is set on the assistant message while we're still receiving
/// chunks from the backend. On rehydrate from Hive we drop streaming-true
/// rows — they represent an interrupted fetch (hot restart mid-stream) and
/// resuming partial responses isn't worth the complexity.
class ChatMessage {
  ChatMessage({
    required this.id,
    required this.role,
    required this.text,
    required this.createdAt,
    this.streaming = false,
  });

  final String id;
  final ChatRole role;
  final String text;
  final DateTime createdAt;
  final bool streaming;

  ChatMessage copyWith({String? text, bool? streaming}) => ChatMessage(
        id: id,
        role: role,
        text: text ?? this.text,
        createdAt: createdAt,
        streaming: streaming ?? this.streaming,
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'role': role.name,
        'text': text,
        'createdAt': createdAt.toIso8601String(),
        if (streaming) 'streaming': true,
      };

  factory ChatMessage.fromJson(Map<String, dynamic> json) {
    return ChatMessage(
      id: json['id'] as String,
      role: ChatRole.values.firstWhere(
        (r) => r.name == json['role'] as String?,
        orElse: () => ChatRole.assistant,
      ),
      text: json['text'] as String? ?? '',
      createdAt: DateTime.parse(json['createdAt'] as String),
      streaming: json['streaming'] as bool? ?? false,
    );
  }
}

enum ChatRole { user, assistant }
