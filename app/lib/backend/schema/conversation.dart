import 'dart:convert';
import 'dart:math';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:url_launcher/url_launcher.dart';

class CreateConversationResponse {
  final List<ServerMessage> messages;
  final ServerConversation? conversation;

  CreateConversationResponse({required this.messages, required this.conversation});

  factory CreateConversationResponse.fromJson(Map<String, dynamic> json) {
    return CreateConversationResponse(
      messages: ((json['messages'] ?? []) as List<dynamic>).map((message) => ServerMessage.fromJson(message)).toList(),
      conversation: json['memory'] != null ? ServerConversation.fromJson(json['memory']) : null,
    );
  }
}

enum ConversationSource { friend, workflow, openglass, screenpipe, sdcard }

class ConversationExternalData {
  final String text;

  ConversationExternalData({required this.text});

  factory ConversationExternalData.fromJson(Map<String, dynamic> json) =>
      ConversationExternalData(text: json['text'] ?? '');

  Map<String, dynamic> toJson() => {'text': text};
}

enum ConversationPostProcessingStatus { not_started, in_progress, completed, canceled, failed }

enum ConversationPostProcessingModel { fal_whisperx, custom_whisperx }

enum ConversationStatus { in_progress, processing, completed, failed }

class ConversationPostProcessing {
  final ConversationPostProcessingStatus status;
  final ConversationPostProcessingModel? model;
  final String? failReason;

  ConversationPostProcessing({required this.status, required this.model, this.failReason});

  factory ConversationPostProcessing.fromJson(Map<String, dynamic> json) {
    return ConversationPostProcessing(
      status: ConversationPostProcessingStatus.values.asNameMap()[json['status']] ??
          ConversationPostProcessingStatus.in_progress,
      model: ConversationPostProcessingModel.values.asNameMap()[json['model']] ??
          ConversationPostProcessingModel.fal_whisperx,
      failReason: json['fail_reason'],
    );
  }

  toJson() => {'status': status.toString().split('.').last, 'model': model.toString().split('.').last};
}

enum ServerProcessingConversationStatus {
  capturing('capturing'),
  processing('processing'),
  done('done'),
  unknown('unknown'),
  ;

  final String value;

  const ServerProcessingConversationStatus(this.value);

  static ServerProcessingConversationStatus valuesFromString(String value) {
    return ServerProcessingConversationStatus.values.firstWhereOrNull((e) => e.value == value) ??
        ServerProcessingConversationStatus.unknown;
  }
}

class ServerConversation {
  final String id;
  final DateTime createdAt;
  final DateTime? startedAt;
  final DateTime? finishedAt;

  final Structured structured;
  final List<TranscriptSegment> transcriptSegments;
  final Geolocation? geolocation;
  final List<ConversationPhoto> photos;

  final List<AppResponse> appResults;
  final ConversationSource? source;
  final String? language; // applies to Friend only

  final ConversationExternalData? externalIntegration;

  ConversationStatus status;
  bool discarded;
  final bool deleted;

  // local label
  bool isNew = false;

  ServerConversation({
    required this.id,
    required this.createdAt,
    required this.structured,
    this.startedAt,
    this.finishedAt,
    this.transcriptSegments = const [],
    this.appResults = const [],
    this.geolocation,
    this.photos = const [],
    this.discarded = false,
    this.deleted = false,
    this.source,
    this.language,
    this.externalIntegration,
    this.status = ConversationStatus.completed,
  });

  factory ServerConversation.fromJson(Map<String, dynamic> json) {
    return ServerConversation(
      id: json['id'],
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      structured: Structured.fromJson(json['structured']),
      startedAt: json['started_at'] != null ? DateTime.parse(json['started_at']).toLocal() : null,
      finishedAt: json['finished_at'] != null ? DateTime.parse(json['finished_at']).toLocal() : null,
      transcriptSegments: ((json['transcript_segments'] ?? []) as List<dynamic>)
          .map((segment) => TranscriptSegment.fromJson(segment))
          .toList(),
      appResults:
          ((json['plugins_results'] ?? []) as List<dynamic>).map((result) => AppResponse.fromJson(result)).toList(),
      geolocation: json['geolocation'] != null ? Geolocation.fromJson(json['geolocation']) : null,
      photos: (json['photos'] as List<dynamic>).map((photo) => ConversationPhoto.fromJson(photo)).toList(),
      discarded: json['discarded'] ?? false,
      source:
          json['source'] != null ? ConversationSource.values.asNameMap()[json['source']] : ConversationSource.friend,
      language: json['language'],
      deleted: json['deleted'] ?? false,
      externalIntegration:
          json['external_data'] != null ? ConversationExternalData.fromJson(json['external_data']) : null,
      status: json['status'] != null
          ? ConversationStatus.values.asNameMap()[json['status']] ?? ConversationStatus.completed
          : ConversationStatus.completed,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toUtc().toIso8601String(),
      'structured': structured.toJson(),
      'started_at': startedAt?.toUtc().toIso8601String(),
      'finished_at': finishedAt?.toUtc().toIso8601String(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'plugins_results': appResults.map((result) => result.toJson()).toList(),
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => photo.toJson()).toList(),
      'discarded': discarded,
      'deleted': deleted,
      'source': source?.toString(),
      'language': language,
      'external_data': externalIntegration?.toJson(),
      'status': status.toString().split('.').last,
    };
  }

  String getTag() {
    if (source == ConversationSource.screenpipe) return 'Screenpipe';
    if (source == ConversationSource.openglass) return 'Openglass';
    if (source == ConversationSource.sdcard) return 'SD Card';
    if (discarded) return 'Discarded';
    return structured.category.substring(0, 1).toUpperCase() + structured.category.substring(1);
  }

  Color getTagTextColor() {
    if (source == ConversationSource.screenpipe) return Colors.deepPurple;
    return Colors.white;
  }

  Color getTagColor() {
    if (source == ConversationSource.screenpipe) return Colors.white;
    return Colors.grey.shade800;
  }

  VoidCallback? onTagPressed(BuildContext context) {
    if (source == ConversationSource.screenpipe) return () => launchUrl(Uri.parse('https://screenpi.pe/'));
    return null;
  }

  String getTranscript({int? maxCount, bool generate = false}) {
    var transcript = TranscriptSegment.segmentsAsString(transcriptSegments, includeTimestamps: true);
    if (maxCount != null) transcript = transcript.substring(0, min(maxCount, transcript.length));
    try {
      return utf8.decode(transcript.codeUnits);
    } catch (e) {
      return transcript;
    }
  }
}

class SyncLocalFilesResponse {
  List<String> newConversationIds = [];
  List<String> updatedConversationIds = [];

  SyncLocalFilesResponse({
    required this.newConversationIds,
    required this.updatedConversationIds,
  });

  factory SyncLocalFilesResponse.fromJson(Map<String, dynamic> json) {
    return SyncLocalFilesResponse(
      newConversationIds: ((json['new_memories'] ?? []) as List<dynamic>).map((val) => val.toString()).toList(),
      updatedConversationIds: ((json['updated_memories'] ?? []) as List<dynamic>).map((val) => val.toString()).toList(),
    );
  }
}

enum SyncedConversationType { newConversation, updatedConversation }

class SyncedConversationPointer {
  final SyncedConversationType type;
  final int index;
  final DateTime key;
  final ServerConversation conversation;

  SyncedConversationPointer({required this.type, required this.index, required this.key, required this.conversation});

  factory SyncedConversationPointer.fromJson(Map<String, dynamic> json) {
    return SyncedConversationPointer(
      type: SyncedConversationType.values.asNameMap()[json['type']] ?? SyncedConversationType.newConversation,
      index: json['index'],
      key: DateTime.parse(json['key']).toLocal(),
      conversation: ServerConversation.fromJson(json['memory']),
    );
  }

  SyncedConversationPointer copyWith(
      {SyncedConversationType? type, int? index, DateTime? key, ServerConversation? conversation}) {
    return SyncedConversationPointer(
      type: type ?? this.type,
      index: index ?? this.index,
      key: key ?? this.key,
      conversation: conversation ?? this.conversation,
    );
  }
}
