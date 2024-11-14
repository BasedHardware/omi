import 'package:collection/collection.dart';
import 'package:uuid/uuid.dart';

enum MessageSender { ai, human }

enum MessageType {
  text('text'),
  daySummary('day_summary'),
  ;

  final String value;

  const MessageType(this.value);

  static MessageType valuesFromString(String value) {
    return MessageType.values.firstWhereOrNull((e) => e.value == value) ?? MessageType.text;
  }
}

class MessageMemoryStructured {
  String title;
  String emoji;

  MessageMemoryStructured(this.title, this.emoji);

  static MessageMemoryStructured fromJson(Map<String, dynamic> json) {
    return MessageMemoryStructured(json['title'], json['emoji']);
  }

  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'emoji': emoji,
    };
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
      DateTime.parse(json['created_at']).toLocal(),
      MessageMemoryStructured.fromJson(json['structured']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toUtc().toIso8601String(),
      'structured': structured.toJson(),
    };
  }
}

class ServerMessage {
  String id;
  DateTime createdAt;
  String text;
  MessageSender sender;
  MessageType type;

  String? appId;
  bool fromIntegration;

  List<MessageMemory> memories;
  bool askForNps = false;

  ServerMessage(
    this.id,
    this.createdAt,
    this.text,
    this.sender,
    this.type,
    this.appId,
    this.fromIntegration,
    this.memories, {
    this.askForNps = false,
  });

  static ServerMessage fromJson(Map<String, dynamic> json) {
    return ServerMessage(
      json['id'],
      DateTime.parse(json['created_at']).toLocal(),
      json['text'] ?? "",
      MessageSender.values.firstWhere((e) => e.toString().split('.').last == json['sender']),
      MessageType.valuesFromString(json['type']),
      json['plugin_id'],
      json['from_integration'] ?? false,
      ((json['memories'] ?? []) as List<dynamic>).map((m) => MessageMemory.fromJson(m)).toList(),
      askForNps: json['ask_for_nps'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toUtc().toIso8601String(),
      'text': text,
      'sender': sender.toString().split('.').last,
      'type': type.toString().split('.').last,
      'plugin_id': appId,
      'from_integration': fromIntegration,
      'memories': memories.map((m) => m.toJson()).toList(),
      'ask_for_nps': askForNps,
    };
  }

  static ServerMessage empty() {
    return ServerMessage(
      '0000',
      DateTime.now(),
      '',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      [],
    );
  }

  static ServerMessage failedMessage() {
    return ServerMessage(
      const Uuid().v4(),
      DateTime.now(),
      'Looks like we are having issues with the server. Please try again later.',
      MessageSender.ai,
      MessageType.text,
      null,
      false,
      [],
    );
  }

  bool get isEmpty => id == '0000';
}
