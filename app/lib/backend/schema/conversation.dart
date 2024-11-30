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
  final ServerConversation? memory;

  CreateConversationResponse({required this.messages, required this.memory});

  factory CreateConversationResponse.fromJson(Map<String, dynamic> json) {
    return CreateConversationResponse(
      messages: ((json['messages'] ?? []) as List<dynamic>).map((message) => ServerMessage.fromJson(message)).toList(),
      memory: json['memory'] != null ? ServerConversation.fromJson(json['memory']) : null,
    );
  }
}

enum ConversationSource { friend, workflow, openglass, screenpipe, sdcard }

class MemoryExternalData {
  final String text;

  MemoryExternalData({required this.text});

  factory MemoryExternalData.fromJson(Map<String, dynamic> json) => MemoryExternalData(text: json['text'] ?? '');

  Map<String, dynamic> toJson() => {'text': text};
}

enum MemoryPostProcessingStatus { not_started, in_progress, completed, canceled, failed }

enum MemoryPostProcessingModel { fal_whisperx, custom_whisperx }

enum MemoryStatus { in_progress, processing, completed, failed }

class MemoryPostProcessing {
  final MemoryPostProcessingStatus status;
  final MemoryPostProcessingModel? model;
  final String? failReason;

  MemoryPostProcessing({required this.status, required this.model, this.failReason});

  factory MemoryPostProcessing.fromJson(Map<String, dynamic> json) {
    return MemoryPostProcessing(
      status: MemoryPostProcessingStatus.values.asNameMap()[json['status']] ?? MemoryPostProcessingStatus.in_progress,
      model: MemoryPostProcessingModel.values.asNameMap()[json['model']] ?? MemoryPostProcessingModel.fal_whisperx,
      failReason: json['fail_reason'],
    );
  }

  toJson() => {'status': status.toString().split('.').last, 'model': model.toString().split('.').last};
}

enum ServerProcessingMemoryStatus {
  capturing('capturing'),
  processing('processing'),
  done('done'),
  unknown('unknown'),
  ;

  final String value;

  const ServerProcessingMemoryStatus(this.value);

  static ServerProcessingMemoryStatus valuesFromString(String value) {
    return ServerProcessingMemoryStatus.values.firstWhereOrNull((e) => e.value == value) ??
        ServerProcessingMemoryStatus.unknown;
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
  final List<MemoryPhoto> photos;

  final List<AppResponse> appResults;
  final ConversationSource? source;
  final String? language; // applies to Friend only

  final MemoryExternalData? externalIntegration;

  MemoryStatus status;
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
    this.status = MemoryStatus.completed,
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
      photos: (json['photos'] as List<dynamic>).map((photo) => MemoryPhoto.fromJson(photo)).toList(),
      discarded: json['discarded'] ?? false,
      source:
          json['source'] != null ? ConversationSource.values.asNameMap()[json['source']] : ConversationSource.friend,
      language: json['language'],
      deleted: json['deleted'] ?? false,
      externalIntegration: json['external_data'] != null ? MemoryExternalData.fromJson(json['external_data']) : null,
      status: json['status'] != null
          ? MemoryStatus.values.asNameMap()[json['status']] ?? MemoryStatus.completed
          : MemoryStatus.completed,
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
  List<String> newMemoryIds = [];
  List<String> updatedMemoryIds = [];

  SyncLocalFilesResponse({
    required this.newMemoryIds,
    required this.updatedMemoryIds,
  });

  factory SyncLocalFilesResponse.fromJson(Map<String, dynamic> json) {
    return SyncLocalFilesResponse(
      newMemoryIds: ((json['new_memories'] ?? []) as List<dynamic>).map((val) => val.toString()).toList(),
      updatedMemoryIds: ((json['updated_memories'] ?? []) as List<dynamic>).map((val) => val.toString()).toList(),
    );
  }
}

enum SyncedConversationType { newConversation, updatedConversation }

class SyncedConversationPointer {
  final SyncedConversationType type;
  final int index;
  final DateTime key;
  final ServerConversation memory;

  SyncedConversationPointer({required this.type, required this.index, required this.key, required this.memory});

  factory SyncedConversationPointer.fromJson(Map<String, dynamic> json) {
    return SyncedConversationPointer(
      type: SyncedConversationType.values.asNameMap()[json['type']] ?? SyncedConversationType.newConversation,
      index: json['index'],
      key: DateTime.parse(json['key']).toLocal(),
      memory: ServerConversation.fromJson(json['memory']),
    );
  }

  SyncedConversationPointer copyWith(
      {SyncedConversationType? type, int? index, DateTime? key, ServerConversation? memory}) {
    return SyncedConversationPointer(
      type: type ?? this.type,
      index: index ?? this.index,
      key: key ?? this.key,
      memory: memory ?? this.memory,
    );
  }
}
