import 'dart:convert';
import 'dart:math';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/geolocation.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/backend/schema/transcript_segment.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:url_launcher/url_launcher.dart';

class CreateMemoryResponse {
  final List<ServerMessage> messages;
  final ServerMemory? memory;

  CreateMemoryResponse({required this.messages, required this.memory});

  factory CreateMemoryResponse.fromJson(Map<String, dynamic> json) {
    return CreateMemoryResponse(
      messages: ((json['messages'] ?? []) as List<dynamic>).map((message) => ServerMessage.fromJson(message)).toList(),
      memory: json['memory'] != null ? ServerMemory.fromJson(json['memory']) : null,
    );
  }
}

enum MemorySource { friend, openglass, screenpipe }

class MemoryExternalData {
  final String text;

  MemoryExternalData({required this.text});

  factory MemoryExternalData.fromJson(Map<String, dynamic> json) => MemoryExternalData(text: json['text'] ?? '');

  Map<String, dynamic> toJson() => {'text': text};
}

enum MemoryPostProcessingStatus { not_started, in_progress, completed, canceled, failed }

enum MemoryPostProcessingModel { fal_whisperx, custom_whisperx }

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

class ServerProcessingMemory {
  final String id;
  final DateTime createdAt;
  final DateTime? startedAt;
  final DateTime? capturingTo;
  final ServerProcessingMemoryStatus? status;
  final List<TranscriptSegment> transcriptSegments;
  final String? memoryId;

  ServerProcessingMemory({
    required this.id,
    required this.createdAt,
    this.startedAt,
    this.capturingTo,
    this.status,
    this.transcriptSegments = const [],
    this.memoryId,
  });

  factory ServerProcessingMemory.fromJson(Map<String, dynamic> json) {
    return ServerProcessingMemory(
      id: json['id'],
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      startedAt: json['started_at'] != null ? DateTime.parse(json['started_at']).toLocal() : null,
      capturingTo: json['capturing_to'] != null ? DateTime.parse(json['capturing_to']).toLocal() : null,
      status: json['status'] != null ? ServerProcessingMemoryStatus.valuesFromString(json['status']) : null,
      transcriptSegments: ((json['transcript_segments'] ?? []) as List<dynamic>)
          .map((segment) => TranscriptSegment.fromJson(segment))
          .toList(),
      memoryId: json['memory_id'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toUtc().toIso8601String(),
      'started_at': startedAt?.toUtc().toIso8601String(),
      'capturing_to': capturingTo?.toUtc().toIso8601String(),
      'status': status.toString(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'memory_id': memoryId,
    };
  }

  String getTag() {
    return 'Processing';
  }

  Color getTagTextColor() {
    return Colors.white;
  }

  Color getTagColor() {
    return Colors.grey.shade800;
  }
}

class ProcessingMemoryResponse {
  final ServerProcessingMemory? result;

  ProcessingMemoryResponse({required this.result});

  factory ProcessingMemoryResponse.fromJson(Map<String, dynamic> json) {
    return ProcessingMemoryResponse(
      result: json['result'] != null ? ServerProcessingMemory.fromJson(json['result']) : null,
    );
  }
}

class UpdateProcessingMemoryResponse {
  final ServerProcessingMemory? result;

  UpdateProcessingMemoryResponse({required this.result});

  factory UpdateProcessingMemoryResponse.fromJson(Map<String, dynamic> json) {
    return UpdateProcessingMemoryResponse(
      result: json['result'] != null ? ServerProcessingMemory.fromJson(json['result']) : null,
    );
  }
}

class ServerMemory {
  final String id;
  final DateTime createdAt;
  final DateTime? startedAt;
  final DateTime? finishedAt;

  final Structured structured;
  final List<TranscriptSegment> transcriptSegments;
  final Geolocation? geolocation;
  final List<MemoryPhoto> photos;

  final List<PluginResponse> pluginsResults;
  final MemorySource? source;
  final String? language; // applies to Friend only

  final MemoryExternalData? externalIntegration;
  // MemoryPostProcessing? postprocessing;
  String? processingMemoryId;

  bool discarded;
  final bool deleted;

  // local failed memories
  final bool failed;
  int retries;

  // local label
  bool isNew = false;

  ServerMemory({
    required this.id,
    required this.createdAt,
    required this.structured,
    this.startedAt,
    this.finishedAt,
    this.transcriptSegments = const [],
    this.pluginsResults = const [],
    this.geolocation,
    this.photos = const [],
    this.discarded = false,
    this.deleted = false,
    this.failed = false,
    this.retries = 0,
    this.source,
    this.language,
    this.externalIntegration,
    // this.postprocessing,
    this.processingMemoryId,
  });

  factory ServerMemory.fromJson(Map<String, dynamic> json) {
    return ServerMemory(
      id: json['id'],
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      structured: Structured.fromJson(json['structured']),
      startedAt: json['started_at'] != null ? DateTime.parse(json['started_at']).toLocal() : null,
      finishedAt: json['finished_at'] != null ? DateTime.parse(json['finished_at']).toLocal() : null,
      transcriptSegments: ((json['transcript_segments'] ?? []) as List<dynamic>)
          .map((segment) => TranscriptSegment.fromJson(segment))
          .toList(),
      pluginsResults:
          ((json['plugins_results'] ?? []) as List<dynamic>).map((result) => PluginResponse.fromJson(result)).toList(),
      geolocation: json['geolocation'] != null ? Geolocation.fromJson(json['geolocation']) : null,
      photos: (json['photos'] as List<dynamic>).map((photo) => MemoryPhoto.fromJson(photo)).toList(),
      discarded: json['discarded'] ?? false,
      source: json['source'] != null ? MemorySource.values.asNameMap()[json['source']] : MemorySource.friend,
      language: json['language'],
      deleted: json['deleted'] ?? false,
      failed: json['failed'] ?? false,
      retries: json['retries'] ?? 0,
      externalIntegration: json['external_data'] != null ? MemoryExternalData.fromJson(json['external_data']) : null,
      // postprocessing: json['postprocessing'] != null ? MemoryPostProcessing.fromJson(json['postprocessing']) : null,
      processingMemoryId: json['processing_memory_id'],
    );
  }

  // bool isPostprocessing() {
  //   int createdSecondsAgo = DateTime.now().difference(createdAt).inSeconds;
  //   return (postprocessing?.status == MemoryPostProcessingStatus.not_started ||
  //           postprocessing?.status == MemoryPostProcessingStatus.in_progress) &&
  //       createdSecondsAgo < 120;
  // }

  // bool isReadyForTranscriptAssignment() {
  //   // TODO: only thing matters here, is if !isPostProcessing() and if we have audio file.
  //   return !discarded && !deleted && !failed && postprocessing?.status == MemoryPostProcessingStatus.completed;
  // }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toUtc().toIso8601String(),
      'structured': structured.toJson(),
      'started_at': startedAt?.toUtc().toIso8601String(),
      'finished_at': finishedAt?.toUtc().toIso8601String(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'plugins_results': pluginsResults.map((result) => result.toJson()).toList(),
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => photo.toJson()).toList(),
      'discarded': discarded,
      'deleted': deleted,
      'source': source?.toString(),
      'language': language,
      'failed': failed,
      'retries': retries,
      'external_data': externalIntegration?.toJson(),
      // 'postprocessing': postprocessing?.toJson(),
      'processing_memory_id': processingMemoryId,
    };
  }

  String getTag() {
    if (source == MemorySource.screenpipe) return 'Screenpipe';
    if (source == MemorySource.openglass) return 'Openglass';
    if (failed) return 'Failed';
    if (discarded) return 'Discarded';
    return structured.category.substring(0, 1).toUpperCase() + structured.category.substring(1);
  }

  Color getTagTextColor() {
    if (source == MemorySource.screenpipe) return Colors.deepPurple;
    return Colors.white;
  }

  Color getTagColor() {
    if (source == MemorySource.screenpipe) return Colors.white;
    return Colors.grey.shade800;
  }

  VoidCallback? onTagPressed(BuildContext context) {
    if (source == MemorySource.screenpipe) return () => launchUrl(Uri.parse('https://screenpi.pe/'));
    if (failed) {
      return () => showDialog(
          builder: (c) => getDialog(context, () => Navigator.pop(context), () => Navigator.pop(context),
              'Failed Memory', 'This memory failed to be created. Will be retried once you reopen the app.',
              singleButton: true, okButtonText: 'OK'),
          context: context);
    }
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
