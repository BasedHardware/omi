class ReplyDraftRequest {
  final String incomingMessage;
  final String? recipientName;
  final String? channel;
  final String? relationship;
  final String? goal;
  final String? extraContext;
  final String tone;
  final String length;
  final bool includeMemories;
  final bool includeRecentChat;

  const ReplyDraftRequest({
    required this.incomingMessage,
    this.recipientName,
    this.channel,
    this.relationship,
    this.goal,
    this.extraContext,
    this.tone = 'natural',
    this.length = 'medium',
    this.includeMemories = true,
    this.includeRecentChat = true,
  });

  Map<String, dynamic> toJson() {
    return {
      'incoming_message': incomingMessage,
      if (recipientName != null && recipientName!.trim().isNotEmpty) 'recipient_name': recipientName!.trim(),
      if (channel != null && channel!.trim().isNotEmpty) 'channel': channel!.trim(),
      if (relationship != null && relationship!.trim().isNotEmpty) 'relationship': relationship!.trim(),
      if (goal != null && goal!.trim().isNotEmpty) 'goal': goal!.trim(),
      if (extraContext != null && extraContext!.trim().isNotEmpty) 'extra_context': extraContext!.trim(),
      'tone': tone,
      'length': length,
      'include_memories': includeMemories,
      'include_recent_chat': includeRecentChat,
    };
  }
}

class ReplyDraftContextSummary {
  final int memoriesUsed;
  final int recentChatMessagesUsed;

  const ReplyDraftContextSummary({
    required this.memoriesUsed,
    required this.recentChatMessagesUsed,
  });

  factory ReplyDraftContextSummary.fromJson(Map<String, dynamic> json) {
    return ReplyDraftContextSummary(
      memoriesUsed: json['memories_used'] ?? 0,
      recentChatMessagesUsed: json['recent_chat_messages_used'] ?? 0,
    );
  }
}

class ReplyDraftResponse {
  final String draft;
  final List<String> alternatives;
  final bool needsReview;
  final List<String> safetyNotes;
  final ReplyDraftContextSummary usedContext;

  const ReplyDraftResponse({
    required this.draft,
    required this.alternatives,
    required this.needsReview,
    required this.safetyNotes,
    required this.usedContext,
  });

  factory ReplyDraftResponse.fromJson(Map<String, dynamic> json) {
    return ReplyDraftResponse(
      draft: json['draft'] ?? '',
      alternatives: ((json['alternatives'] ?? []) as List).map((item) => item.toString()).toList(),
      needsReview: json['needs_review'] ?? true,
      safetyNotes: ((json['safety_notes'] ?? []) as List).map((item) => item.toString()).toList(),
      usedContext: ReplyDraftContextSummary.fromJson(
        json['used_context'] ?? {},
      ),
    );
  }
}
