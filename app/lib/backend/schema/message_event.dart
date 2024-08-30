enum MessageEventType {
  newMemoryCreating('new_memory_creating'),
  newMemoryCreated('new_memory_created'),
  newMemoryCreateFailed('new_memory_create_failed'),
  memoryPostProcessingSuccess('memory_post_processing_success'),
  memoryPostProcessingFailed('memory_post_processing_failed'),
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
  MessageEventType type;

  ServerMessageEvent(
    this.type,
    this.memoryId,
  );

  static ServerMessageEvent fromJson(Map<String, dynamic> json) {
    return ServerMessageEvent(
      MessageEventType.valuesFromString(json['type']),
      json['memory_id'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': type,
      'memory_id': memoryId,
    };
  }
}
