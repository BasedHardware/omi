import 'dart:convert';

import 'package:flutter/foundation.dart';

/// This cut proves native audio ingress, not a durable recording.
class CaptureIngressHealth {
  static const hideUnverifiedListening = true;
  static const cccdRecoveryReason = 'cccd_timeout_recovery';

  const CaptureIngressHealth({
    required this.phase,
    required this.generation,
    required this.reason,
    required this.validUntilMs,
    required this.subscriptionConfirmed,
    required this.unverifiedSinceMs,
    this.lastAudioAtMs = 0,
    this.recoveryOutcome = 'none',
    this.recoverySpent = false,
    this.reconnectSpent = false,
  });

  final String phase;
  final String generation;
  final String reason;
  final int validUntilMs;
  final bool subscriptionConfirmed;
  final int unverifiedSinceMs;

  /// When audio last arrived on the current connection generation, or 0 if it
  /// never did. Native resets it on every generation change (and on a failed
  /// subscription), so a non-zero value proves the link of this generation has
  /// delivered audio — the difference between healthy silence and a
  /// confirmed-but-never-delivering subscription.
  final int lastAudioAtMs;

  final String recoveryOutcome;
  final bool recoverySpent;
  final bool reconnectSpent;

  /// Whether this snapshot proves the pendant is capturing. A flowing lease is
  /// one proof; a confirmed-subscription quiet that already delivered audio in
  /// this generation is the other: the pendant only sends audio while there is
  /// sound, so silence after sound is healthy listening, not a lapsed link.
  /// A quiet with no audio this generation proves nothing — a subscription the
  /// pendant never delivered on is exactly the wedge the wait grace exists for.
  /// Waits, repairs, reconnects and exhausted recoveries are not proofs either.
  bool verifiedAt(DateTime now) =>
      subscriptionConfirmed && (audioLeaseValid(now) || (phase == 'quiet' && lastAudioAtMs > 0));

  /// A current audio lease: audio actually arrived, and recently. The proof a
  /// zero-byte dispute (a wedge episode) still needs — a confirmed subscription
  /// alone does not show the link delivers, which is exactly what it disputes.
  bool audioLeaseValid(DateTime now) =>
      phase == 'flowing' && subscriptionConfirmed && now.millisecondsSinceEpoch < validUntilMs;

  /// Native recovery is exhausted and audio still is not arriving. Only the
  /// user can restore the link; surfaces may say so and offer a reconnect.
  bool get actionable => phase == 'actionRequired';

  static CaptureIngressHealth? parse(String json) {
    try {
      final data = jsonDecode(json) as Map<String, dynamic>;
      return CaptureIngressHealth(
        phase: data['phase'] as String,
        generation: data['generation'] as String,
        reason: data['reason'] as String,
        validUntilMs: data['valid_until_ms'] as int,
        subscriptionConfirmed: data['subscription_confirmed'] as bool,
        unverifiedSinceMs: data['unverified_since_ms'] as int,
        lastAudioAtMs: data['last_audio_at_ms'] as int? ?? 0,
        recoveryOutcome: data['recovery_outcome'] as String? ?? 'none',
        recoverySpent: data['recovery_spent'] as bool? ?? false,
        reconnectSpent: data['reconnect_spent'] as bool? ?? false,
      );
    } catch (_) {
      return null;
    }
  }
}

/// Optional seam while iOS Omi adopts ingress truth. Other adapters keep their
/// existing behavior; implementing this port does not grant them a health claim.
abstract interface class CaptureIngressPort {
  bool get supportsIngressHealth;
  CaptureIngressHealth? ingressHealth(String deviceId);
  void addIngressListener(VoidCallback listener);
  void removeIngressListener(VoidCallback listener);
  Future<void> setCaptureAuthorized(String deviceId, bool authorized);
}

extension CaptureIngressVerification on CaptureIngressPort {
  // Android supplies health only for CCCD recovery; healthy captures keep their existing policy.
  bool requiresVerification(String deviceId) =>
      supportsIngressHealth || ingressHealth(deviceId)?.reason == CaptureIngressHealth.cccdRecoveryReason;
}
