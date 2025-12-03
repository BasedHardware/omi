import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/backend/schema/schema.dart';
import 'package:omi/env/env.dart';

/// Conversation merge API client functions
///
/// Provides 4 merge-related API calls:
/// 1. previewMerge - Preview merge without committing
/// 2. mergeConversations - Execute merge with rollback
/// 3. rollbackMerge - Undo merge within 24h
/// 4. getMergeHistory - Get recent merge operations

// ==================== Response Models ====================

class MergeMetadata {
  final int totalSegments;
  final double totalDurationSeconds;
  final int actionItemsCombined;
  final int actionItemsDeduplicated;
  final int eventsCombined;
  final int photosCombined;
  final int audioFilesCombined;
  final int estimatedProcessingTimeSeconds;

  MergeMetadata({
    required this.totalSegments,
    required this.totalDurationSeconds,
    required this.actionItemsCombined,
    required this.actionItemsDeduplicated,
    required this.eventsCombined,
    this.photosCombined = 0,
    this.audioFilesCombined = 0,
    this.estimatedProcessingTimeSeconds = 5,
  });

  factory MergeMetadata.fromJson(Map<String, dynamic> json) {
    return MergeMetadata(
      totalSegments: json['total_segments'] ?? 0,
      totalDurationSeconds: (json['total_duration_seconds'] ?? 0).toDouble(),
      actionItemsCombined: json['action_items_combined'] ?? 0,
      actionItemsDeduplicated: json['action_items_deduplicated'] ?? 0,
      eventsCombined: json['events_combined'] ?? 0,
      photosCombined: json['photos_combined'] ?? 0,
      audioFilesCombined: json['audio_files_combined'] ?? 0,
      estimatedProcessingTimeSeconds: json['estimated_processing_time_seconds'] ?? 5,
    );
  }
}

class MergePreviewResponse {
  final Map<String, dynamic> previewConversation;
  final List<ServerConversation> sourceConversations;
  final MergeMetadata mergeMetadata;
  final List<String> warnings;

  MergePreviewResponse({
    required this.previewConversation,
    required this.sourceConversations,
    required this.mergeMetadata,
    this.warnings = const [],
  });

  factory MergePreviewResponse.fromJson(Map<String, dynamic> json) {
    return MergePreviewResponse(
      previewConversation: json['preview_conversation'] ?? {},
      sourceConversations:
          (json['source_conversations'] as List<dynamic>?)?.map((conv) => ServerConversation.fromJson(conv)).toList() ??
              [],
      mergeMetadata: MergeMetadata.fromJson(json['merge_metadata'] ?? {}),
      warnings: (json['warnings'] as List<dynamic>?)?.map((w) => w.toString()).toList() ?? [],
    );
  }
}

class MergeConversationsResponse {
  final ServerConversation mergedConversation;
  final String mergeId;
  final DateTime rollbackAvailableUntil;
  final MergeMetadata mergeMetadata;

  MergeConversationsResponse({
    required this.mergedConversation,
    required this.mergeId,
    required this.rollbackAvailableUntil,
    required this.mergeMetadata,
  });

  String get mergedConversationId => mergedConversation.id;

  factory MergeConversationsResponse.fromJson(Map<String, dynamic> json) {
    final rollbackUntil = DateTime.tryParse(json['rollback_available_until'] ?? '');
    if (json['merged_conversation'] == null || rollbackUntil == null) {
      throw FormatException('Invalid API response for MergeConversationsResponse. Received: $json');
    }
    return MergeConversationsResponse(
      mergedConversation: ServerConversation.fromJson(json['merged_conversation']),
      mergeId: json['merge_id'] ?? '',
      rollbackAvailableUntil: rollbackUntil.toLocal(),
      mergeMetadata: MergeMetadata.fromJson(json['merge_metadata'] ?? {}),
    );
  }
}

class RollbackMergeResponse {
  final List<ServerConversation> restoredConversations;
  final String mergeId;
  final DateTime rollbackTime;

  RollbackMergeResponse({
    required this.restoredConversations,
    required this.mergeId,
    required this.rollbackTime,
  });

  factory RollbackMergeResponse.fromJson(Map<String, dynamic> json) {
    final rollbackTime = DateTime.tryParse(json['rollback_time'] ?? '');
    if (rollbackTime == null) {
      throw FormatException('Invalid API response for RollbackMergeResponse: missing rollback_time. Received: $json');
    }
    return RollbackMergeResponse(
      restoredConversations: (json['restored_conversations'] as List<dynamic>?)
              ?.map((conv) => ServerConversation.fromJson(conv))
              .toList() ??
          [],
      mergeId: json['merge_id'] ?? '',
      rollbackTime: rollbackTime.toLocal(),
    );
  }
}

// ==================== API Functions ====================

/// Preview conversation merge without committing changes
///
/// Returns a preview of what the merged conversation will look like,
/// including AI-generated title, overview, and metadata about the merge.
///
/// This is a read-only operation - no database changes are made.
Future<MergePreviewResponse?> previewMerge(List<String> conversationIds) async {
  if (conversationIds.length < 2) {
    debugPrint('previewMerge: Need at least 2 conversations');
    return null;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/merge/preview',
    headers: {},
    method: 'POST',
    body: jsonEncode({
      'conversation_ids': conversationIds,
    }),
  );

  if (response == null) return null;
  debugPrint('previewMerge: ${response.statusCode}');

  if (response.statusCode == 200) {
    return MergePreviewResponse.fromJson(jsonDecode(response.body));
  } else if (response.statusCode == 400) {
    debugPrint('previewMerge validation failed: ${response.body}');
    return null;
  } else {
    debugPrint('previewMerge error ${response.statusCode}: ${response.body}');
    return null;
  }
}

/// Execute conversation merge with rollback capability
///
/// Combines multiple conversations into one merged conversation.
/// Source conversations are marked as merged (soft deleted).
/// Creates a rollback snapshot valid for 24 hours.
///
/// [conversationIds]: List of conversation IDs to merge (min 2, must be adjacent)
/// [customTitle]: Optional custom title (overrides AI-generated title)
///
/// Returns MergeConversationsResponse with merged conversation and merge_id for rollback
Future<MergeConversationsResponse?> mergeConversations(
  List<String> conversationIds, {
  String? customTitle,
}) async {
  if (conversationIds.length < 2) {
    debugPrint('mergeConversations: Need at least 2 conversations');
    return null;
  }

  Map<String, dynamic> body = {
    'conversation_ids': conversationIds,
  };
  if (customTitle != null && customTitle.isNotEmpty) {
    body['custom_title'] = customTitle;
  }

  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/merge',
    headers: {},
    method: 'POST',
    body: jsonEncode(body),
  );

  if (response == null) return null;
  debugPrint('mergeConversations: ${response.statusCode}');

  if (response.statusCode == 200) {
    return MergeConversationsResponse.fromJson(jsonDecode(response.body));
  } else if (response.statusCode == 400) {
    debugPrint('mergeConversations validation failed: ${response.body}');
    return null;
  } else if (response.statusCode == 500) {
    debugPrint('mergeConversations server error: ${response.body}');
    return null;
  } else {
    debugPrint('mergeConversations error ${response.statusCode}: ${response.body}');
    return null;
  }
}

/// Rollback a conversation merge within 24-hour window
///
/// Restores source conversations and deletes the merged conversation.
/// Only works if rollback window hasn't expired and merge wasn't already rolled back.
///
/// [mergeId]: Merge operation ID (from mergeConversations response)
///
/// Returns RollbackMergeResponse with restored conversations
Future<RollbackMergeResponse?> rollbackMerge(String mergeId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/merge/$mergeId/rollback',
    headers: {},
    method: 'POST',
    body: '',
  );

  if (response == null) return null;
  debugPrint('rollbackMerge: ${response.statusCode}');

  if (response.statusCode == 200) {
    return RollbackMergeResponse.fromJson(jsonDecode(response.body));
  } else if (response.statusCode == 400) {
    debugPrint('rollbackMerge not available: ${response.body}');
    return null;
  } else if (response.statusCode == 404) {
    debugPrint('rollbackMerge: Merge history not found');
    return null;
  } else {
    debugPrint('rollbackMerge error ${response.statusCode}: ${response.body}');
    return null;
  }
}

/// Unmerge a merged conversation by its conversation ID
///
/// Convenience wrapper that looks up the merge by conversation ID
/// and calls the rollback endpoint.
///
/// [conversationId]: The merged conversation ID
///
/// Returns RollbackMergeResponse with restored conversations
Future<RollbackMergeResponse?> unmergeConversation(String conversationId) async {
  var response = await makeApiCall(
    url: '${Env.apiBaseUrl}v1/conversations/$conversationId/unmerge',
    headers: {},
    method: 'POST',
    body: '',
  );

  if (response == null) return null;
  debugPrint('unmergeConversation: ${response.statusCode}');

  if (response.statusCode == 200) {
    return RollbackMergeResponse.fromJson(jsonDecode(response.body));
  } else if (response.statusCode == 400) {
    debugPrint('unmergeConversation not available: ${response.body}');
    return null;
  } else if (response.statusCode == 404) {
    debugPrint('unmergeConversation: Conversation not found or not merged');
    return null;
  } else {
    debugPrint('unmergeConversation error ${response.statusCode}: ${response.body}');
    return null;
  }
}
