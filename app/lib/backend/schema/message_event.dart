import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';

enum MessageEventType {
  // newMemoryCreating('new_memory_creating'),
  // newMemoryCreated('new_memory_created'),
  conversationCreated('memory_created'),
  newConversationCreateFailed('new_memory_create_failed'),
  newProcessingConversationCreated('new_processing_memory_created'),
  conversationProcessingStarted('memory_processing_started'),
  processingConversationStatusChanged('processing_memory_status_changed'),
  ping('ping'),
  conversationBackwardSynced('memory_backward_synced'),
  serviceStatus('service_status'),
  lastConversation('last_memory'),
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
  ServerConversation? conversation;
  List<ServerMessage>? messages;
  String? name;
  String? status;
  String? statusText;
  String? memoryId;

  ServerMessageEvent(
    this.type,
    this.conversation,
    this.messages,
    this.name,
    this.status,
    this.statusText,
    this.memoryId,
  );

  static ServerMessageEvent fromJson(Map<String, dynamic> json) {
    return ServerMessageEvent(
      MessageEventType.valuesFromString(json['type']),
      // json['memory_id'],
      // json['processing_memory_id'],
      json['memory'] != null ? ServerConversation.fromJson(json['memory']) : null,
      ((json['messages'] ?? []) as List<dynamic>).map((message) => ServerMessage.fromJson(message)).toList(),
      // json['processing_memory_status'] != null
      //     ? ServerProcessingMemoryStatus.valuesFromString(json['processing_memory_status'])
      //     : null,

      json['name'],
      json['status'],
      json['status_text'],
      json['memory_id'],
    );
  }
}
