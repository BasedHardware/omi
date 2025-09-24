// import 'package:collection/collection.dart';

class ChatSession {
  final String id;
  final String? appId; // Nullable for OMI app sessions
  final String? title;
  final DateTime createdAt;

  ChatSession({
    required this.id,
    required this.createdAt,
    this.appId,
    this.title,
  });

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    // Support possible snake_case keys from backend
    final createdAtRaw = json['created_at'] ?? json['createdAt'];
    return ChatSession(
      id: json['id'],
      appId: json['app_id'] ?? json['appId'],
      title: json['title'],
      createdAt: createdAtRaw != null ? DateTime.parse(createdAtRaw as String).toLocal() : DateTime.now(),
    );
  }

  static List<ChatSession> fromJsonList(List<dynamic> json) {
    return json.map((e) => ChatSession.fromJson(e as Map<String, dynamic>)).toList();
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'app_id': appId,
      'title': title,
      'created_at': createdAt.toUtc().toIso8601String(),
    }..removeWhere((key, value) => value == null);
  }
}
