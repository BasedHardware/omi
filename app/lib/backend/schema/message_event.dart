import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

enum MessageEventType {
  // newMemoryCreating('new_memory_creating'),
  // newMemoryCreated('new_memory_created'),
  conversationCreated('conversation_created'),
  newConversationCreateFailed('new_conversation_create_failed'),
  newProcessingConversationCreated('new_processing_conversation_created'),
  conversationProcessingStarted('conversation_processing_started'),
  processingConversationStatusChanged('processing_conversation_status_changed'),
  ping('ping'),
  conversationBackwardSynced('conversation_backward_synced'),
  serviceStatus('service_status'),
  lastConversation('last_conversation'),
  translating('translating'),
  unknown('unknown'),
  ;

  final String value;
  const MessageEventType(this.value);

  static MessageEventType valuesFromString(String value) {
    // Mapping of old event names to new event names
    const Map<String, String> eventRenameMapping = {
      "memory_created": "conversation_created",
      "new_memory_create_failed": "new_conversation_create_failed",
      "new_processing_memory_created": "new_processing_conversation_created",
      "memory_processing_started": "conversation_processing_started",
      "processing_memory_status_changed": "processing_conversation_status_changed",
      "memory_backward_synced": "conversation_backward_synced",
      "last_memory": "last_conversation",
    };

    // Check if the event name is in the mapping, otherwise use the original value
    String mappedValue = eventRenameMapping[value] ?? value;

    return MessageEventType.values.firstWhere(
      (e) => e.value == mappedValue,
      orElse: () => MessageEventType.unknown,
    );
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
  List<TranscriptSegment>? segments;

  ServerMessageEvent(
    this.type,
    this.conversation,
    this.messages,
    this.name,
    this.status,
    this.statusText,
    this.memoryId,
    this.segments,
  );

  static ServerMessageEvent fromJson(Map<String, dynamic> json) {
    return ServerMessageEvent(
      MessageEventType.valuesFromString(json['type']),
      // json['memory_id'],
      // json['processing_memory_id'],
      json['memory'] != null
          ? ServerConversation.fromJson(json['memory'])
          : (json['conversation'] != null ? ServerConversation.fromJson(json['conversation']) : null),
      ((json['messages'] ?? []) as List<dynamic>).map((message) => ServerMessage.fromJson(message)).toList(),
      // json['processing_memory_status'] != null
      //     ? ServerProcessingMemoryStatus.valuesFromString(json['processing_memory_status'])
      //     : null,

      json['name'],
      json['status'],
      json['status_text'],
      json['memory_id'] ?? json['conversation_id'],
      json['segments'] != null 
          ? (json['segments'] as List<dynamic>).map((segment) => TranscriptSegment.fromJson(segment)).toList()
          : null,
    );
  }
}
