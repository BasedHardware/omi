import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';

import 'package:collection/collection.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:omi/backend/schema/gen/conversation_wire.g.dart' as wire;
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/utils/audio/audio_timeline_mapper.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';

class CreateConversationResponse {
  final List<ServerMessage> messages;
  final ServerConversation? conversation;

  CreateConversationResponse({required this.messages, required this.conversation});

  factory CreateConversationResponse.fromJson(Map<String, dynamic> json) {
    return CreateConversationResponse.fromGeneratedWireJson(json);
  }

  factory CreateConversationResponse.fromGeneratedWireJson(Map<String, dynamic> json) {
    return CreateConversationResponse(
      messages: ((json['messages'] ?? []) as List<dynamic>)
          .map((message) => ServerMessage.fromGeneratedWireJson(message as Map<String, dynamic>))
          .toList(),
      conversation: json['conversation'] != null
          ? ServerConversation.fromJson(json['conversation'] as Map<String, dynamic>)
          : (json['memory'] != null ? ServerConversation.fromJson(json['memory'] as Map<String, dynamic>) : null),
    );
  }
}

enum ConversationSource {
  friend,
  omi,
  workflow,
  openglass,
  screenpipe,
  sdcard,
  fieldy,
  bee,
  xor,
  frame,
  friend_com,
  apple_watch,
  phone,
  desktop,
  limitless,
  rayban_meta,
}

class ConversationExternalData {
  final String text;

  ConversationExternalData({required this.text});

  factory ConversationExternalData.fromJson(Map<String, dynamic> json) =>
      ConversationExternalData(text: json['text'] ?? '');

  Map<String, dynamic> toJson() => {'text': text};
}

// ignore: constant_identifier_names
enum ConversationVisibility {
  private_('private'),
  shared('shared');

  final String value;
  const ConversationVisibility(this.value);

  static ConversationVisibility fromString(String? s) {
    if (s == private_.value) return private_;
    if (s == shared.value) return shared;
    if (s == 'public') return shared;
    return private_;
  }
}

enum ConversationPostProcessingStatus { not_started, in_progress, completed, canceled, failed }

enum ConversationPostProcessingModel { fal_whisperx, custom_whisperx }

enum ConversationStatus { in_progress, processing, merging, completed, failed }

class ConversationPostProcessing {
  final ConversationPostProcessingStatus status;
  final ConversationPostProcessingModel? model;
  final String? failReason;

  ConversationPostProcessing({required this.status, required this.model, this.failReason});

  factory ConversationPostProcessing.fromJson(Map<String, dynamic> json) {
    return ConversationPostProcessing(
      status:
          ConversationPostProcessingStatus.values.asNameMap()[json['status']] ??
          ConversationPostProcessingStatus.in_progress,
      model:
          ConversationPostProcessingModel.values.asNameMap()[json['model']] ??
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
  unknown('unknown');

  final String value;

  const ServerProcessingConversationStatus(this.value);

  static ServerProcessingConversationStatus valuesFromString(String value) {
    return ServerProcessingConversationStatus.values.firstWhereOrNull((e) => e.value == value) ??
        ServerProcessingConversationStatus.unknown;
  }
}

class ConversationPhoto {
  String id;
  final String base64;
  String? description;
  final DateTime createdAt;
  bool discarded;

  ConversationPhoto({
    required this.id,
    required this.base64,
    this.description,
    required this.createdAt,
    this.discarded = false,
  });

  factory ConversationPhoto.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedConversationPhoto.fromJson(json);
    return ConversationPhoto.fromGenerated(generated);
  }

  factory ConversationPhoto.fromGenerated(wire.GeneratedConversationPhoto generated) {
    return ConversationPhoto(
      id: generated.id ?? '',
      base64: generated.base64,
      description: generated.description,
      createdAt: generated.createdAt ?? DateTime.now(),
      discarded: generated.discarded,
    );
  }

  wire.GeneratedConversationPhoto toGenerated() {
    return wire.GeneratedConversationPhoto(
      id: id,
      base64: base64,
      description: description,
      createdAt: createdAt,
      discarded: discarded,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

/// Links a conversation to a Google Calendar event.
class CalendarEventLink {
  final String eventId;
  final String title;
  final List<String> attendees;
  final List<String> attendeeEmails;
  final DateTime startTime;
  final DateTime endTime;
  final String? htmlLink;

  CalendarEventLink({
    required this.eventId,
    required this.title,
    this.attendees = const [],
    this.attendeeEmails = const [],
    required this.startTime,
    required this.endTime,
    this.htmlLink,
  });

  factory CalendarEventLink.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedCalendarEventLink.fromJson(json);
    return CalendarEventLink.fromGenerated(generated);
  }

  factory CalendarEventLink.fromGenerated(wire.GeneratedCalendarEventLink generated) {
    return CalendarEventLink(
      eventId: generated.eventId,
      title: generated.title,
      attendees: generated.attendees,
      attendeeEmails: generated.attendeeEmails,
      startTime: generated.startTime,
      endTime: generated.endTime,
      htmlLink: generated.htmlLink,
    );
  }

  wire.GeneratedCalendarEventLink toGenerated() {
    return wire.GeneratedCalendarEventLink(
      eventId: eventId,
      title: title,
      attendees: attendees,
      attendeeEmails: attendeeEmails,
      startTime: startTime,
      endTime: endTime,
      htmlLink: htmlLink,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

class AudioFile {
  final String id;
  final String uid;
  final String conversationId;
  final List<double> chunkTimestamps;
  final String provider;
  final DateTime? startedAt;
  final double duration;

  AudioFile({
    required this.id,
    required this.uid,
    required this.conversationId,
    required this.chunkTimestamps,
    this.provider = 'gcp',
    this.startedAt,
    required this.duration,
  });

  factory AudioFile.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedAudioFile.fromJson(json);
    return AudioFile.fromGenerated(generated);
  }

  factory AudioFile.fromGenerated(wire.GeneratedAudioFile generated) {
    return AudioFile(
      id: generated.id,
      uid: generated.uid,
      conversationId: generated.conversationId,
      chunkTimestamps: generated.chunkTimestamps,
      provider: generated.provider,
      startedAt: generated.startedAt,
      duration: generated.duration,
    );
  }

  wire.GeneratedAudioFile toGenerated() {
    return wire.GeneratedAudioFile(
      id: id,
      uid: uid,
      conversationId: conversationId,
      chunkTimestamps: chunkTimestamps,
      provider: provider,
      startedAt: startedAt,
      duration: duration,
    );
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}

TranscriptSegment _transcriptSegmentFromGenerated(wire.GeneratedTranscriptSegment generated) {
  return TranscriptSegment.fromGenerated(generated);
}

/// Conversation-level dense playback artifact stamp: one MP3 per conversation
/// (inter-part gaps collapsed) + the spans manifest for wall-clock mapping.
class ConversationAudioInfo {
  final double duration; // wall-clock seconds
  final double capturedDuration; // seconds of actual audio
  final List<ConversationAudioSpan> spans;

  ConversationAudioInfo({required this.duration, required this.capturedDuration, this.spans = const []});

  factory ConversationAudioInfo.fromGenerated(wire.GeneratedConversationAudio generated) {
    return ConversationAudioInfo(
      duration: generated.duration,
      capturedDuration: generated.capturedDuration,
      spans: generated.spans
          .map(
            (s) => ConversationAudioSpan(
              fileId: s.fileId,
              wallOffset: s.wallOffset,
              artifactOffset: s.artifactOffset,
              len: s.len,
            ),
          )
          .toList(),
    );
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
  final List<AudioFile> audioFiles;
  final ConversationAudioInfo? conversationAudio;

  final List<AppResponse> appResults;
  final List<String> suggestedSummarizationApps;
  final ConversationSource? source;
  final String? language; // applies to friend/omi only

  final ConversationExternalData? externalIntegration;

  /// Calendar event link - set when conversation overlaps with a Google Calendar event
  final CalendarEventLink? calendarEvent;

  ConversationStatus status;
  bool discarded;
  final bool deleted;
  final bool isLocked;
  bool starred;
  String? folderId;
  ConversationVisibility visibility;

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
    this.suggestedSummarizationApps = const [],
    this.geolocation,
    this.photos = const [],
    this.audioFiles = const [],
    this.conversationAudio,
    this.discarded = false,
    this.deleted = false,
    this.source,
    this.language,
    this.externalIntegration,
    this.calendarEvent,
    this.status = ConversationStatus.completed,
    this.isLocked = false,
    this.starred = false,
    this.folderId,
    this.visibility = ConversationVisibility.private_,
  });

  factory ServerConversation.fromJson(Map<String, dynamic> json) {
    final normalized = Map<String, dynamic>.from(json);
    final structured = json['structured'] is Map<String, dynamic> ? Structured.fromJson(json['structured']) : null;
    if (structured != null) {
      normalized['structured'] = structured.toGenerated().toJson();
    }
    // Legacy caches (< toJson wire-format fix) wrote plugins_results entries as
    // {'appId', 'content'}; the wire parser requires the plugin_id key.
    final rawPluginResults = normalized['plugins_results'];
    if (rawPluginResults is List) {
      normalized['plugins_results'] = rawPluginResults.map((entry) {
        if (entry is Map<String, dynamic> && !entry.containsKey('plugin_id')) {
          return {...entry, 'plugin_id': entry['appId'] ?? entry['app_id']};
        }
        return entry;
      }).toList();
    }
    final generated = wire.GeneratedConversation.fromJson(normalized);
    return ServerConversation.fromGenerated(
      generated,
      structured: structured,
      geolocation: json['geolocation'] is Map<String, dynamic> ? Geolocation.fromJson(json['geolocation']) : null,
      deleted: json['deleted'] ?? false,
    );
  }

  factory ServerConversation.fromGenerated(
    wire.GeneratedConversation generated, {
    Structured? structured,
    Geolocation? geolocation,
    bool deleted = false,
  }) {
    return ServerConversation(
      id: generated.id,
      createdAt: generated.createdAt,
      structured: structured ?? Structured.fromGenerated(generated.structured),
      startedAt: generated.startedAt,
      finishedAt: generated.finishedAt,
      transcriptSegments: generated.transcriptSegments.map(_transcriptSegmentFromGenerated).toList(),
      appResults: generated.appsResults.isNotEmpty
          ? generated.appsResults.map(AppResponse.fromGenerated).toList()
          : generated.pluginsResults.map((result) => AppResponse(result.content, appId: result.pluginId)).toList(),
      suggestedSummarizationApps: generated.suggestedSummarizationApps,
      geolocation:
          geolocation ?? (generated.geolocation == null ? null : Geolocation.fromGenerated(generated.geolocation!)),
      photos: generated.photos.map(ConversationPhoto.fromGenerated).toList(),
      audioFiles: generated.audioFiles.map(AudioFile.fromGenerated).toList(),
      conversationAudio: generated.conversationAudio == null
          ? null
          : ConversationAudioInfo.fromGenerated(generated.conversationAudio!),
      discarded: generated.discarded,
      source: generated.source != null
          ? ConversationSource.values.asNameMap()[generated.source]
          : ConversationSource.omi,
      language: generated.language,
      deleted: deleted,
      externalIntegration: generated.externalData != null
          ? ConversationExternalData.fromJson(generated.externalData!)
          : null,
      calendarEvent: generated.calendarEvent == null ? null : CalendarEventLink.fromGenerated(generated.calendarEvent!),
      status: generated.status != null
          ? ConversationStatus.values.asNameMap()[generated.status] ?? ConversationStatus.completed
          : ConversationStatus.completed,
      isLocked: generated.isLocked,
      starred: generated.starred,
      folderId: generated.folderId,
      visibility: ConversationVisibility.fromString(generated.visibility),
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
      'apps_results': appResults.map((result) => result.toGenerated().toJson()).toList(),
      'plugins_results': appResults.map((result) {
        return wire.GeneratedPluginResult(pluginId: result.appId, content: result.content).toJson();
      }).toList(),
      'suggested_summarization_apps': suggestedSummarizationApps,
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => photo.toJson()).toList(),
      'discarded': discarded,
      'deleted': deleted,
      'source': source?.toString(),
      'language': language,
      'external_data': externalIntegration?.toJson(),
      'calendar_event': calendarEvent?.toJson(),
      'status': status.toString().split('.').last,
      'is_locked': isLocked,
      'starred': starred,
      'folder_id': folderId,
      'visibility': visibility.value,
    };
  }

  wire.GeneratedConversation toGenerated() {
    return wire.GeneratedConversation(
      id: id,
      createdAt: createdAt,
      startedAt: startedAt,
      finishedAt: finishedAt,
      structured: structured.toGenerated(),
      transcriptSegments: transcriptSegments.map((segment) => segment.toGenerated()).toList(),
      appsResults: appResults.map((result) => result.toGenerated()).toList(),
      pluginsResults: appResults.map((result) {
        return wire.GeneratedPluginResult(pluginId: result.appId, content: result.content);
      }).toList(),
      suggestedSummarizationApps: suggestedSummarizationApps,
      geolocation: geolocation?.toGenerated(),
      photos: photos.map((photo) => photo.toGenerated()).toList(),
      audioFiles: audioFiles.map((audioFile) => audioFile.toGenerated()).toList(),
      discarded: discarded,
      source: source?.name,
      language: language,
      externalData: externalIntegration?.toJson(),
      calendarEvent: calendarEvent?.toGenerated(),
      status: status.name,
      isLocked: isLocked,
      starred: starred,
      folderId: folderId,
      visibility: visibility.value,
    );
  }

  int unassignedSegmentsLength() {
    return transcriptSegments.where((element) => (element.personId == null && !element.isUser)).length;
  }

  int speakerWithMostUnassignedSegments() {
    var speakers = transcriptSegments
        .where((element) => element.personId == null && !element.isUser)
        .map((e) => e.speakerId)
        .toList();
    if (speakers.isEmpty) return -1;
    var segmentsBySpeakers = groupBy(
      speakers,
      (e) => e,
    ).entries.reduce((a, b) => a.value.length > b.value.length ? a : b).key;
    return segmentsBySpeakers;
  }

  int firstSegmentIndexForSpeaker(int speakerId) {
    return transcriptSegments.indexWhere((element) => element.speakerId == speakerId);
  }

  String getTag() {
    if (source == ConversationSource.screenpipe) return 'Screenpipe';
    if (source == ConversationSource.openglass) return 'OmiGlass';
    if (source == ConversationSource.rayban_meta) return 'Ray-Ban Meta';
    if (source == ConversationSource.sdcard) return 'SD Card';
    if (discarded) return 'Discarded';
    if (structured.category.isEmpty) return 'Other';
    return structured.category.substring(0, 1).toUpperCase() + structured.category.substring(1);
  }

  Color getTagTextColor() {
    if (source == ConversationSource.screenpipe) return Colors.deepPurple;
    return Colors.white;
  }

  Color getTagColor() {
    if (source == ConversationSource.screenpipe) return Colors.white;
    return const Color(0xFF35343B);
  }

  VoidCallback? onTagPressed(BuildContext context) {
    if (source == ConversationSource.screenpipe) return () => launchUrl(Uri.parse('https://screenpi.pe/'));
    return null;
  }

  String getTranscript({int? maxCount, bool generate = false}) {
    var transcript = TranscriptSegment.segmentsAsString(transcriptSegments, includeTimestamps: true);
    if (maxCount != null && transcript.isNotEmpty) {
      transcript = transcript.substring(max(transcript.length - maxCount, 0));
    }
    try {
      return utf8.decode(transcript.codeUnits);
    } catch (e) {
      return transcript;
    }
  }

  int getDurationInSeconds() {
    // started_at is the streaming-session origin, not this conversation's start,
    // so finishedAt - startedAt over-counts; prefer the transcript span (#4056).
    if (transcriptSegments.isEmpty && finishedAt != null && startedAt != null) {
      return finishedAt!.difference(startedAt!).inSeconds;
    }
    return _getDurationInSecondsByTranscripts();
  }

  /// Calculates the conversation duration in seconds based on transcript segments
  int _getDurationInSecondsByTranscripts() {
    if (transcriptSegments.isEmpty) return 0;

    // Find the last segment's end time
    double lastEndTime = 0;
    for (var segment in transcriptSegments) {
      if (segment.end > lastEndTime) {
        lastEndTime = segment.end;
      }
    }

    return lastEndTime.toInt();
  }

  /// Check if this conversation has audio files available
  bool hasAudio() => audioFiles.isNotEmpty;

  /// Get the primary audio file (first one)
  AudioFile? getPrimaryAudioFile() => audioFiles.isNotEmpty ? audioFiles.first : null;
}

class SyncLocalFilesResponse {
  List<String> newConversationIds = [];
  List<String> updatedConversationIds = [];
  int failedSegments;
  int totalSegments;
  List<String> errors;

  /// Client-side batches that could not be uploaded. Unlike [failedSegments],
  /// these failures leave WALs retryable locally and must re-arm foreground
  /// recovery rather than presenting a completed sync.
  int localUploadFailures;

  SyncLocalFilesResponse({
    required this.newConversationIds,
    required this.updatedConversationIds,
    this.failedSegments = 0,
    this.totalSegments = 0,
    this.errors = const [],
    this.localUploadFailures = 0,
  });

  bool get hasPartialFailure => failedSegments > 0;

  factory SyncLocalFilesResponse.fromJson(Map<String, dynamic> json) {
    return SyncLocalFilesResponse.fromGenerated(wire.GeneratedSyncLocalFilesResultResponse.fromJson(json));
  }

  factory SyncLocalFilesResponse.fromGenerated(wire.GeneratedSyncLocalFilesResultResponse generated) {
    return SyncLocalFilesResponse(
      newConversationIds: generated.newMemories ?? [],
      updatedConversationIds: generated.updatedMemories ?? [],
      failedSegments: generated.failedSegments,
      totalSegments: generated.totalSegments,
      errors: generated.errors ?? [],
    );
  }
}

class SyncJobStartResponse {
  final String jobId;
  final String status;
  final int totalFiles;
  final int totalSegments;
  final int pollAfterMs;

  SyncJobStartResponse({
    required this.jobId,
    required this.status,
    required this.totalFiles,
    required this.totalSegments,
    required this.pollAfterMs,
  });

  factory SyncJobStartResponse.fromJson(Map<String, dynamic> json) {
    return SyncJobStartResponse.fromGenerated(wire.GeneratedSyncJobStartResponse.fromJson(json));
  }

  factory SyncJobStartResponse.fromGenerated(wire.GeneratedSyncJobStartResponse generated) {
    return SyncJobStartResponse(
      jobId: generated.jobId,
      status: generated.status,
      totalFiles: generated.totalFiles,
      totalSegments: generated.totalSegments,
      pollAfterMs: generated.pollAfterMs,
    );
  }
}

class SyncJobStatusResponse {
  final String jobId;
  final String status;
  final int totalSegments;
  final int processedSegments;
  final int successfulSegments;
  final int failedSegments;
  final SyncLocalFilesResponse? result;
  final String? error;
  final String? lane;
  final String? reasonCode;
  final int? retryAfter;

  SyncJobStatusResponse({
    required this.jobId,
    required this.status,
    this.totalSegments = 0,
    this.processedSegments = 0,
    this.successfulSegments = 0,
    this.failedSegments = 0,
    this.result,
    this.error,
    this.lane,
    this.reasonCode,
    this.retryAfter,
  });

  bool get isTerminal => status == 'completed' || status == 'partial_failure' || status == 'failed';
  bool get isSuccess => status == 'completed';
  bool get isPartialFailure => status == 'partial_failure';

  factory SyncJobStatusResponse.fromJson(Map<String, dynamic> json) {
    final generated = wire.GeneratedSyncJobStatusResponse.fromJson(json);
    return SyncJobStatusResponse(
      jobId: generated.jobId,
      status: generated.status,
      totalSegments: generated.totalSegments,
      processedSegments: generated.processedSegments,
      successfulSegments: generated.successfulSegments,
      failedSegments: generated.failedSegments,
      result: generated.result == null ? null : SyncLocalFilesResponse.fromGenerated(generated.result!),
      error: generated.error,
      lane: json['lane'] as String?,
      reasonCode: json['reason_code'] as String?,
      retryAfter: (json['retry_after'] as num?)?.toInt(),
    );
  }

  factory SyncJobStatusResponse.fromGenerated(wire.GeneratedSyncJobStatusResponse generated) {
    return SyncJobStatusResponse(
      jobId: generated.jobId,
      status: generated.status,
      totalSegments: generated.totalSegments,
      processedSegments: generated.processedSegments,
      successfulSegments: generated.successfulSegments,
      failedSegments: generated.failedSegments,
      result: generated.result == null ? null : SyncLocalFilesResponse.fromGenerated(generated.result!),
      error: generated.error,
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

  SyncedConversationPointer copyWith({
    SyncedConversationType? type,
    int? index,
    DateTime? key,
    ServerConversation? conversation,
  }) {
    return SyncedConversationPointer(
      type: type ?? this.type,
      index: index ?? this.index,
      key: key ?? this.key,
      conversation: conversation ?? this.conversation,
    );
  }
}
