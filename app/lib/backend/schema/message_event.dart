import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';

enum MessageEventType {
  newMemoryCreating('new_memory_creating'),
  newMemoryCreated('new_memory_created'),
  newMemoryCreateFailed('new_memory_create_failed'),
  memoryPostProcessingSuccess('memory_post_processing_success'),
  memoryPostProcessingFailed('memory_post_processing_failed'),
  newProcessingMemoryCreated('new_processing_memory_created'),
  ping('ping'),
  unknown('unknown'),
  ;

  final String value;
  const MessageEventType(this.value);

  static MessageEventType valuesFromString(String value) {
    return MessageEventType.values.firstWhere((e) => e.value == value, orElse: () => MessageEventType.unknown);
  }
}

class ServerMessageEvent {
  MessageEventType type;
  String? memoryId;
  String? processingMemoryId;
  ServerMemory? memory;
  List<ServerMessage>? messages;

  ServerMessageEvent(
    this.type,
    this.memoryId,
    this.processingMemoryId,
    this.memory,
    this.messages,
  );

  static ServerMessageEvent fromJson(Map<String, dynamic> json) {
    return ServerMessageEvent(
      MessageEventType.valuesFromString(json['type']),
      json['memory_id'],
      json['processing_memory_id'],
      json['memory'] != null ? ServerMemory.fromJson(json['memory']) : null,
      ((json['messages'] ?? []) as List<dynamic>).map((message) => ServerMessage.fromJson(message)).toList(),
    );
  }
}
