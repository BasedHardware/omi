enum MessageSender { ai, human }

enum MessageType { text, daySummary }

class MessageMemoryStructured {
  String title;
  String emoji;

  MessageMemoryStructured(this.title, this.emoji);

  static MessageMemoryStructured fromJson(Map<String, dynamic> json) {
    return MessageMemoryStructured(json['title'], json['emoji']);
  }
}

class MessageMemory {
  String id;
  DateTime createdAt;
  MessageMemoryStructured structured;

  MessageMemory(this.id, this.createdAt, this.structured);

  static MessageMemory fromJson(Map<String, dynamic> json) {
    return MessageMemory(
      json['id'],
      DateTime.parse(json['created_at']),
      MessageMemoryStructured.fromJson(json['structured']),
    );
  }
}

class ServerMessage {
  String id;
  DateTime createdAt;
  String text;
  MessageSender sender;
  MessageType type;

  String? pluginId;
  bool fromIntegration;

  List<MessageMemory> memories;

  ServerMessage(
    this.id,
    this.createdAt,
    this.text,
    this.sender,
    this.type,
    this.pluginId,
    this.fromIntegration,
    this.memories,
  );

  static ServerMessage fromJson(Map<String, dynamic> json) {
    return ServerMessage(
      json['id'],
      DateTime.parse(json['created_at']),
      json['text'],
      MessageSender.values.firstWhere((e) => e.toString().split('.').last == json['sender']),
      MessageType.values.firstWhere((e) => e.toString().split('.').last == json['type']),
      json['plugin_id'],
      json['from_integration'] ?? false,
      ((json['memories'] ?? []) as List<dynamic>).map((m) => MessageMemory.fromJson(m)).toList(),
    );
  }
}
