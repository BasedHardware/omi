import 'package:omi/backend/schema/gen/subscription_usage_wire.g.dart' as wire;

/// Client view of S16's one allowance answer.
///
/// Modes match `resolve_transcription_allowance`: `managed`, `on_device`, `blocked`.
/// This type does not re-derive the answer. It only carries what the snapshot said.
class TranscriptionAllowanceSnapshot {
  static const modeManaged = 'managed';
  static const modeOnDevice = 'on_device';
  static const modeBlocked = 'blocked';

  final String mode;
  final String reason;
  final int? remainingSeconds;

  const TranscriptionAllowanceSnapshot({
    required this.mode,
    required this.reason,
    this.remainingSeconds,
  });

  bool get isManaged => mode == modeManaged;
  bool get isOnDevice => mode == modeOnDevice;
  bool get isBlocked => mode == modeBlocked;

  factory TranscriptionAllowanceSnapshot.fromGenerated(wire.GeneratedTranscriptionAllowanceSnapshot generated) {
    return TranscriptionAllowanceSnapshot(
      mode: generated.mode,
      reason: generated.reason,
      remainingSeconds: generated.remainingSeconds,
    );
  }

  wire.GeneratedTranscriptionAllowanceSnapshot toGenerated() {
    return wire.GeneratedTranscriptionAllowanceSnapshot(
      mode: mode,
      reason: reason,
      remainingSeconds: remainingSeconds,
    );
  }

  factory TranscriptionAllowanceSnapshot.fromJson(Map<String, dynamic> json) {
    return TranscriptionAllowanceSnapshot.fromGenerated(wire.GeneratedTranscriptionAllowanceSnapshot.fromJson(json));
  }

  Map<String, dynamic> toJson() => toGenerated().toJson();
}
