import 'package:omi/backend/schema/gen/reply_drafts_wire.g.dart' as wire;

// Hand surface over the generated wire DTOs (reply_drafts_wire.g.dart). The wire
// types own JSON decoding/encoding; these adapters keep the app-facing shape the
// UI depends on (non-null alternatives/safety notes, draft validation, and request
// trimming) while delegating parsing to the generated code, so this file stays
// generated-backed against the app-client OpenAPI contract.

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

  factory ReplyDraftContextSummary.fromGenerated(wire.GeneratedReplyDraftContextSummary g) {
    return ReplyDraftContextSummary(
      memoriesUsed: g.memoriesUsed,
      recentChatMessagesUsed: g.recentChatMessagesUsed,
    );
  }

  factory ReplyDraftContextSummary.fromJson(Map<String, dynamic> json) =>
      ReplyDraftContextSummary.fromGenerated(wire.GeneratedReplyDraftContextSummary.fromJson(json));
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

  factory ReplyDraftResponse.fromGenerated(wire.GeneratedReplyDraftResponse g) {
    if (g.draft.trim().isEmpty) {
      throw const FormatException('Reply draft response is missing a draft.');
    }
    return ReplyDraftResponse(
      draft: g.draft.trim(),
      alternatives: (g.alternatives ?? const <String>[]).map((item) => item.toString()).toList(),
      needsReview: g.needsReview,
      safetyNotes: (g.safetyNotes ?? const <String>[]).map((item) => item.toString()).toList(),
      usedContext: ReplyDraftContextSummary.fromGenerated(g.usedContext),
    );
  }

  factory ReplyDraftResponse.fromJson(Map<String, dynamic> json) {
    // Preserve the app-facing contract: a missing or blank draft is a hard error,
    // validated before delegating the full parse to the generated wire decoder.
    final draft = json['draft'];
    if (draft is! String || draft.trim().isEmpty) {
      throw const FormatException('Reply draft response is missing a draft.');
    }
    return ReplyDraftResponse.fromGenerated(wire.GeneratedReplyDraftResponse.fromJson(json));
  }
}
