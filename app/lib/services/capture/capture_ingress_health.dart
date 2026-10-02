import 'dart:convert';

import 'package:flutter/foundation.dart';

/// This cut proves native audio ingress, not a durable recording.
class CaptureIngressHealth {
  static const hideUnverifiedListening = true;

  const CaptureIngressHealth({
    required this.phase,
    required this.generation,
    required this.reason,
    required this.validUntilMs,
    required this.subscriptionConfirmed,
    required this.unverifiedSinceMs,
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
  final String recoveryOutcome;
  final bool recoverySpent;
  final bool reconnectSpent;

  bool verifiedAt(DateTime now) =>
      phase == 'flowing' && subscriptionConfirmed && now.millisecondsSinceEpoch < validUntilMs;

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
