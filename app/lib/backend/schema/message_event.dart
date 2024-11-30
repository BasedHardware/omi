import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/backend/schema/message.dart';

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
  // String? memoryId;
  // String? processingMemoryId;
  ServerConversation? conversation;
  List<ServerMessage>? messages;
  // ServerProcessingMemoryStatus? processingMemoryStatus;
  String? name;

  ServerMessageEvent(
    this.type,
    // this.memoryId,
    // this.processingMemoryId,
    this.conversation,
    this.messages,
    // this.processingMemoryStatus,
    this.name,
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
    );
  }
}
