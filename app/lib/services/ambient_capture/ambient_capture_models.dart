import 'package:omi/services/ambient_capture/ambient_capture_health.dart';

enum AmbientFallbackSource { localStt, accessibilityCaption, liveCaption, manualNote, gapMarker }

class AmbientFallbackSegment {
  final String text;
  final AmbientFallbackSource source;
  final DateTime start;
  final DateTime end;
  final double? confidence;
  final AmbientCaptureHealthState healthState;
  final String? foregroundAppPackage;
  final bool rawAudioAvailable;
  final bool uploadedToOmi;

  const AmbientFallbackSegment({
    required this.text,
    required this.source,
    required this.start,
    required this.end,
    this.confidence,
    required this.healthState,
    this.foregroundAppPackage,
    required this.rawAudioAvailable,
    this.uploadedToOmi = false,
  });

  AmbientFallbackSegment copyWith({bool? uploadedToOmi}) {
    return AmbientFallbackSegment(
      text: text,
      source: source,
      start: start,
      end: end,
      confidence: confidence,
      healthState: healthState,
      foregroundAppPackage: foregroundAppPackage,
      rawAudioAvailable: rawAudioAvailable,
      uploadedToOmi: uploadedToOmi ?? this.uploadedToOmi,
    );
  }

  factory AmbientFallbackSegment.fromJson(Map<String, dynamic> json) {
    return AmbientFallbackSegment(
      text: json['text']?.toString() ?? '',
      source: AmbientFallbackSource.values.firstWhere(
        (s) => s.name == json['source'],
        orElse: () => AmbientFallbackSource.gapMarker,
      ),
      start: DateTime.parse(json['start']),
      end: DateTime.parse(json['end']),
      confidence: (json['confidence'] as num?)?.toDouble(),
      healthState: AmbientCaptureHealthState.fromWire(json['health_state']?.toString()),
      foregroundAppPackage: json['foreground_app_package']?.toString(),
      rawAudioAvailable: json['raw_audio_available'] as bool? ?? false,
      uploadedToOmi: json['uploaded_to_omi'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'text': text,
      'source': source.name,
      'start': start.toUtc().toIso8601String(),
      'end': end.toUtc().toIso8601String(),
      if (confidence != null) 'confidence': confidence,
      'health_state': healthState.wireName,
      if (foregroundAppPackage != null) 'foreground_app_package': foregroundAppPackage,
      'raw_audio_available': rawAudioAvailable,
      'uploaded_to_omi': uploadedToOmi,
    };
  }
}

class AmbientCaptureSession {
  final String id;
  final DateTime startedAt;
  final DateTime? stoppedAt;
  final AmbientCaptureHealthState lastHealthState;

  const AmbientCaptureSession({
    required this.id,
    required this.startedAt,
    this.stoppedAt,
    required this.lastHealthState,
  });
}

class AmbientCaptureGap {
  final DateTime start;
  final DateTime end;
  final AmbientCaptureHealthState healthState;

  const AmbientCaptureGap({required this.start, required this.end, required this.healthState});
}

class AmbientCaptureTelemetryEvent {
  final String type;
  final DateTime timestamp;
  final Map<String, dynamic> metadata;

  const AmbientCaptureTelemetryEvent({required this.type, required this.timestamp, this.metadata = const {}});

  factory AmbientCaptureTelemetryEvent.fromJson(Map<dynamic, dynamic> json) {
    final millis = json['timestamp'] is int ? json['timestamp'] as int : DateTime.now().millisecondsSinceEpoch;
    return AmbientCaptureTelemetryEvent(
      type: json['type']?.toString() ?? 'unknown',
      timestamp: DateTime.fromMillisecondsSinceEpoch(millis),
      metadata: Map<String, dynamic>.from(json)..remove('type')..remove('timestamp'),
    );
  }
}

class AmbientSpoolFile {
  final String sessionId;
  final DateTime startedAt;
  final String filePath;
  final int bytes;
  final double durationEstimate;
  final String status;

  const AmbientSpoolFile({
    required this.sessionId,
    required this.startedAt,
    required this.filePath,
    required this.bytes,
    required this.durationEstimate,
    required this.status,
  });

  bool get isPending => status != 'synced' && status != 'imported';

  factory AmbientSpoolFile.fromJson(Map<dynamic, dynamic> json) {
    final started = (json['started_at'] as num?)?.toInt() ?? 0;
    return AmbientSpoolFile(
      sessionId: json['session_id']?.toString() ?? '',
      startedAt: DateTime.fromMillisecondsSinceEpoch(started * 1000),
      filePath: json['file_path']?.toString() ?? '',
      bytes: (json['bytes'] as num?)?.toInt() ?? 0,
      durationEstimate: (json['duration_estimate'] as num?)?.toDouble() ?? 0,
      status: json['status']?.toString() ?? 'pending',
    );
  }
}
