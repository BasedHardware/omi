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
  String? memoryId;
  String? processingMemoryId;
  MessageEventType type;

  ServerMessageEvent(
    this.type,
    this.memoryId,
    this.processingMemoryId,
  );

  static ServerMessageEvent fromJson(Map<String, dynamic> json) {
    return ServerMessageEvent(
      MessageEventType.valuesFromString(json['type']),
      json['memory_id'],
      json['processing_memory_id'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': type,
      'memory_id': memoryId,
      'processing_memory_id': processingMemoryId,
    };
  }
}
