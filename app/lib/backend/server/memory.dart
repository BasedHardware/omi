import 'package:friend_private/backend/server/photo.dart';
import 'package:friend_private/backend/server/structured.dart';
import 'package:friend_private/backend/server/transcript_segment.dart';

class Memory {
  final String id;
  final DateTime createdAt;
  final String transcript;
  final Structured structured;
  final DateTime? startedAt;
  final DateTime? finishedAt;
  final List<TranscriptSegment> transcriptSegments;
  final List<PluginResult> pluginsResults;
  final Geolocation? geolocation;
  final List<MemoryPhoto> photos;
  final bool discarded;
  final bool deleted;

  Memory({
    required this.id,
    required this.createdAt,
    required this.transcript,
    required this.structured,
    this.startedAt,
    this.finishedAt,
    this.transcriptSegments = const [],
    this.pluginsResults = const [],
    this.geolocation,
    this.photos = const [],
    this.discarded = false,
    this.deleted = false,
  });

  factory Memory.fromJson(Map<String, dynamic> json) {
    return Memory(
      id: json['id'],
      createdAt: DateTime.parse(json['created_at']),
      transcript: json['transcript'],
      structured: Structured.fromJson(json['structured']),
      startedAt: json['started_at'] != null ? DateTime.parse(json['started_at']) : null,
      finishedAt: json['finished_at'] != null ? DateTime.parse(json['finished_at']) : null,
      transcriptSegments: ((json['transcript_segments'] ?? []) as List<dynamic>)
          .map((segment) => TranscriptSegment.fromJson(segment))
          .toList(),
      pluginsResults:
          ((json['plugins_results'] ?? []) as List<dynamic>).map((result) => PluginResult.fromJson(result)).toList(),
      geolocation: json['geolocation'] != null ? Geolocation.fromJson(json['geolocation']) : null,
      photos: (json['photos'] as List<dynamic>).map((photo) => MemoryPhoto.fromJson(photo)).toList(),
      discarded: json['discarded'] ?? false,
      deleted: json['deleted'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'created_at': createdAt.toIso8601String(),
      'transcript': transcript,
      'structured': structured.toJson(),
      'started_at': startedAt?.toIso8601String(),
      'finished_at': finishedAt?.toIso8601String(),
      'transcript_segments': transcriptSegments.map((segment) => segment.toJson()).toList(),
      'plugins_results': pluginsResults.map((result) => result.toJson()).toList(),
      'geolocation': geolocation?.toJson(),
      'photos': photos.map((photo) => photo.toJson()).toList(),
      'discarded': discarded,
      'deleted': deleted,
    };
  }
}

class PluginResult {
  final String? pluginId;
  final String content;

  PluginResult({
    this.pluginId,
    required this.content,
  });

  factory PluginResult.fromJson(Map<String, dynamic> json) {
    return PluginResult(
      pluginId: json['plugin_id'],
      content: json['content'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'plugin_id': pluginId,
      'content': content,
    };
  }
}

class Geolocation {
  final String googlePlaceId;
  final double latitude;
  final double longitude;
  final double? altitude;
  final double? accuracy;
  final String address;
  final String locationType;

  Geolocation({
    required this.googlePlaceId,
    required this.latitude,
    required this.longitude,
    this.altitude,
    this.accuracy,
    required this.address,
    required this.locationType,
  });

  factory Geolocation.fromJson(Map<String, dynamic> json) {
    return Geolocation(
      googlePlaceId: json['google_place_id'],
      latitude: json['latitude'],
      longitude: json['longitude'],
      altitude: json['altitude'],
      accuracy: json['accuracy'],
      address: json['address'],
      locationType: json['location_type'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'google_place_id': googlePlaceId,
      'latitude': latitude,
      'longitude': longitude,
      'altitude': altitude,
      'accuracy': accuracy,
      'address': address,
      'location_type': locationType,
    };
  }
}
