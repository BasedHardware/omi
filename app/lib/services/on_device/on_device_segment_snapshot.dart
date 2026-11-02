import 'package:omi/backend/schema/transcript_segment.dart';

/// The durable request input for an immutable continuation session. A retry
/// must not run a speech model again and change an already accepted chunk.
class OnDeviceSegmentSnapshot {
  OnDeviceSegmentSnapshot(
      {required this.segments, required this.duration, required this.language, required this.engine, this.projection});
  final List<TranscriptSegment> segments;
  final double duration;
  final String language, engine;
  final Map<String, dynamic>? projection;

  factory OnDeviceSegmentSnapshot.fromJson(Map<String, dynamic> json) {
    try {
      final duration = (json['duration'] as num).toDouble();
      final segments = (json['segments'] as List)
          .map((s) => TranscriptSegment.fromJson(Map<String, dynamic>.from(s as Map)))
          .toList();
      if (segments.isEmpty || !duration.isFinite || duration <= 0) {
        throw const FormatException('Invalid prepared transcript');
      }
      return OnDeviceSegmentSnapshot(
          segments: segments,
          duration: duration,
          language: json['language'] as String,
          engine: json['engine'] as String,
          projection: json['projection'] is Map ? Map<String, dynamic>.from(json['projection'] as Map) : null);
    } catch (_) {
      // Bad local metadata retains the source audio and never logs transcript content.
      throw const FormatException('Invalid prepared transcript');
    }
  }

  Map<String, dynamic> toJson() => {
        'segments': segments.map((s) => s.toJson()).toList(),
        'duration': duration,
        'language': language,
        'engine': engine,
        if (projection != null) 'projection': projection
      };
}
