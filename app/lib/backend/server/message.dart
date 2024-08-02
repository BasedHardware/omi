enum MessageSender { ai, human }

enum MessageType { text, daySummary }

class ServerMessage {
  String id;
  DateTime createdAt;
  String text;
  MessageSender sender;
  MessageType type;

  String? pluginId;
  bool fromIntegration;

  // List<String> memoriesId;

  ServerMessage(
    this.id,
    this.createdAt,
    this.text,
    this.sender,
    this.type,
    this.pluginId,
    this.fromIntegration,
    // this.memoriesId = const [],
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
      // json['memories_id'].cast<String>(),
    );
  }
}
