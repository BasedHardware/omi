import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/database/geolocation.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/transcript_segment.dart';
import 'package:friend_private/backend/schema/message.dart';
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

  bool discarded;
  final bool deleted;

  // local failed memories
  final bool failed;
  int retries;

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
  });

  factory ServerMemory.fromJson(Map<String, dynamic> json) {
    return ServerMemory(
      id: json['id'],
      createdAt: DateTime.parse(json['created_at']).toLocal(),
      structured: Structured.fromJson(json['structured']),
      startedAt: json['started_at'] != null ? DateTime.parse(json['started_at']) : null,
      finishedAt: json['finished_at'] != null ? DateTime.parse(json['finished_at']) : null,
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
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toIso8601String(),
      'structured': structured.toJson(),
      'started_at': startedAt?.toIso8601String(),
      'finished_at': finishedAt?.toIso8601String(),
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
