// Shared synthetic native-event vector schema for phone-mic capture (C3/C5).
//
// The vector mirrors the Pigeon `PhoneMicFlutterApi` contract 1:1 — session
// ids on every event, states named exactly as `PhoneMicCaptureState`
// (`idle|starting|running|interrupted|rebuilding`), stream frames as PCM16LE
// mono 16kHz — so the SAME vectors replay through:
//
// - the Dart seam (drive `NativeMicRecorderService` handlers directly), and
// - C5's thin Swift/Kotlin seams (re-emit each step through the native
//   module's event path).
//
// No Pigeon surface changes: this is an adapter over the existing contract.
library;

import 'dart:convert';
import 'dart:typed_data';

const String nativeEventVectorSchemaVersion = 'phone-mic-native-events/v1';

/// Event kinds, one per `PhoneMicFlutterApi` method.
enum NativeCaptureEventKind { audioFrame, stateChanged, captureError, batchProgress }

class NativeCaptureEvent {
  final NativeCaptureEventKind kind;

  /// The session the event belongs to. Replays must deliver this unchanged:
  /// the receiver's session-identity gate is under test.
  final int sessionId;

  /// `PhoneMicCaptureState` name — required for [NativeCaptureEventKind.stateChanged].
  /// `idle` is the terminal state.
  final String? state;

  /// PCM16LE mono 16kHz frame bytes — required for [NativeCaptureEventKind.audioFrame].
  final List<int>? pcmFrame;

  /// Required for [NativeCaptureEventKind.batchProgress].
  final double? capturedSeconds;

  /// Required for [NativeCaptureEventKind.captureError].
  final String? errorCode;
  final String? errorMessage;

  const NativeCaptureEvent({
    required this.kind,
    required this.sessionId,
    this.state,
    this.pcmFrame,
    this.capturedSeconds,
    this.errorCode,
    this.errorMessage,
  });

  factory NativeCaptureEvent.state(String state, int sessionId) =>
      NativeCaptureEvent(kind: NativeCaptureEventKind.stateChanged, sessionId: sessionId, state: state);

  factory NativeCaptureEvent.frame(List<int> pcm, int sessionId) =>
      NativeCaptureEvent(kind: NativeCaptureEventKind.audioFrame, sessionId: sessionId, pcmFrame: pcm);

  factory NativeCaptureEvent.error(String code, String message, int sessionId) => NativeCaptureEvent(
      kind: NativeCaptureEventKind.captureError, sessionId: sessionId, errorCode: code, errorMessage: message);

  factory NativeCaptureEvent.batchProgress(double seconds, int sessionId) =>
      NativeCaptureEvent(kind: NativeCaptureEventKind.batchProgress, sessionId: sessionId, capturedSeconds: seconds);

  Map<String, Object?> toJson() => {
        'kind': kind.name,
        'session_id': sessionId,
        if (state != null) 'state': state,
        if (pcmFrame != null) 'pcm_frame_base64': base64Encode(pcmFrame!),
        if (capturedSeconds != null) 'captured_seconds': capturedSeconds,
        if (errorCode != null) 'error_code': errorCode,
        if (errorMessage != null) 'error_message': errorMessage,
      };

  factory NativeCaptureEvent.fromJson(Map<String, dynamic> json) => NativeCaptureEvent(
        kind: NativeCaptureEventKind.values.byName(json['kind'] as String),
        sessionId: json['session_id'] as int,
        state: json['state'] as String?,
        pcmFrame: json['pcm_frame_base64'] == null ? null : base64Decode(json['pcm_frame_base64'] as String),
        capturedSeconds: (json['captured_seconds'] as num?)?.toDouble(),
        errorCode: json['error_code'] as String?,
        errorMessage: json['error_message'] as String?,
      );
}

/// A replayable vector: an ordered sequence of native events with deterministic
/// synthetic audio. Revisions are immutable — change content, bump revision.
class NativeEventVector {
  final String id;
  final int revision;
  final String schemaVersion;
  final int startSessionId;
  final List<NativeCaptureEvent> events;

  const NativeEventVector({
    required this.id,
    required this.revision,
    required this.startSessionId,
    required this.events,
    this.schemaVersion = nativeEventVectorSchemaVersion,
  });

  Map<String, Object?> toJson() => {
        'id': id,
        'revision': revision,
        'schema_version': schemaVersion,
        'start_session_id': startSessionId,
        'events': events.map((e) => e.toJson()).toList(),
      };

  String toJsonString() => const JsonEncoder.withIndent('  ').convert(toJson());

  factory NativeEventVector.fromJson(Map<String, dynamic> json) => NativeEventVector(
        id: json['id'] as String,
        revision: json['revision'] as int,
        startSessionId: json['start_session_id'] as int,
        events: (json['events'] as List)
            .map((e) => NativeCaptureEvent.fromJson(Map<String, dynamic>.from(e as Map)))
            .toList(),
      );

  /// Deterministic synthetic PCM16 mono-16k frame (320 bytes = 10ms).
  ///
  /// Sample values come from a per-frame seeded 16-bit LCG — no random source,
  /// no customer audio, identical bytes on every host and run. The first byte
  /// of each frame carries the frame index mod 256 so injected audio is
  /// traceable through WAL files and upload records after replay.
  static Uint8List synthesizePcmFrame(int frameIndex) {
    final bytes = Uint8List(320);
    bytes[0] = frameIndex & 0xFF;
    var state = 0x4D45 ^ (frameIndex * 2654435761) & 0xFFFF;
    for (var i = 2; i < 320; i += 2) {
      state = (1103515245 * state + 12345) & 0xFFFF;
      bytes[i] = state & 0xFF;
      bytes[i + 1] = (state >> 8) & 0xFF;
    }
    return bytes;
  }
}
