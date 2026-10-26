// A confirmed-subscription quiet is healthy listening, not a lapsed link (the pendant sends
// audio only while there is sound); only a wait or an exhausted recovery may stop the clock,
// and only a real failure may warn. Pins the state mapping of #20378 as revised for silence.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/capture/capture_ingress_health.dart';
import 'package:omi/services/telemetry/client_telemetry_schema.dart';

void main() {
  final now = DateTime.utc(2026, 10, 26, 3, 25);

  CaptureIngressHealth health({
    required String phase,
    bool subscriptionConfirmed = true,
    int validUntilMs = 0,
  }) =>
      CaptureIngressHealth(
        phase: phase,
        generation: 'gen',
        reason: 'test',
        validUntilMs: validUntilMs,
        subscriptionConfirmed: subscriptionConfirmed,
        unverifiedSinceMs: 0,
      );

  group('CaptureIngressHealth.verifiedAt', () {
    test('a flowing lease within its lifetime verifies', () {
      final valid = now.millisecondsSinceEpoch + 30000;
      expect(health(phase: 'flowing', validUntilMs: valid).verifiedAt(now), isTrue);
    });

    test('a confirmed-subscription quiet verifies, whatever the lease says', () {
      // Native quiet (fresh_subscription_quiet, budget_spent_quiet) has no audio lease:
      // last_audio_at is nil, so valid_until_ms is 0. Silence is not a lapse.
      expect(health(phase: 'quiet', validUntilMs: 0).verifiedAt(now), isTrue);
      expect(health(phase: 'quiet', validUntilMs: now.millisecondsSinceEpoch - 60000).verifiedAt(now), isTrue);
    });

    test('quiet without a confirmed subscription does not verify', () {
      expect(health(phase: 'quiet', subscriptionConfirmed: false).verifiedAt(now), isFalse);
    });

    test('a wait, a repair, a reconnect and an exhausted recovery do not verify', () {
      for (final phase in ['inactive', 'unverified', 'repairing', 'reconnecting', 'actionRequired']) {
        expect(health(phase: phase, validUntilMs: now.millisecondsSinceEpoch + 30000).verifiedAt(now), isFalse,
            reason: phase);
      }
    });

    test('an expired flowing lease does not verify until native settles it', () {
      expect(
        health(phase: 'flowing', validUntilMs: now.millisecondsSinceEpoch - 1).verifiedAt(now),
        isFalse,
      );
    });

    test('parses the native snapshot shape', () {
      final parsed = CaptureIngressHealth.parse(jsonEncode({
        'phase': 'quiet',
        'generation': 'gen',
        'reason': 'fresh_subscription_quiet',
        'valid_until_ms': 0,
        'subscription_confirmed': true,
        'unverified_since_ms': 0,
      }));
      expect(parsed, isNotNull);
      expect(parsed!.verifiedAt(now), isTrue);
      expect(parsed.actionable, isFalse);
      final failed = CaptureIngressHealth.parse(jsonEncode({
        'phase': 'actionRequired',
        'generation': 'gen',
        'reason': 'recovery_incomplete_budget_spent',
        'valid_until_ms': 0,
        'subscription_confirmed': false,
        'unverified_since_ms': 1,
      }));
      expect(failed!.actionable, isTrue);
      expect(failed.verifiedAt(now), isFalse);
    });
  });

  group('ClientTelemetrySchema ingress phases', () {
    test('every native OmiCaptureHealth phase maps to itself (wire snake case)', () {
      const native = ['inactive', 'unverified', 'flowing', 'repairing', 'reconnecting', 'quiet'];
      for (final phase in native) {
        expect(ClientTelemetrySchema.mapIngressPhase(phase), phase);
        expect(ClientTelemetrySchema.ingressPhaseMapped(phase), isTrue, reason: phase);
      }
      expect(ClientTelemetrySchema.mapIngressPhase('actionRequired'), 'action_required');
      expect(ClientTelemetrySchema.ingressPhaseMapped('actionRequired'), isTrue);
    });

    test('legacy emitters stay accepted and unknown phases still report unmapped', () {
      for (final legacy in ['subscribing', 'awaiting_audio', 'recovering', 'disconnected', 'flowing']) {
        expect(ClientTelemetrySchema.ingressPhaseMapped(legacy), isTrue, reason: legacy);
      }
      expect(ClientTelemetrySchema.mapIngressPhase('nonsense'), 'unknown');
      expect(ClientTelemetrySchema.ingressPhaseMapped('nonsense'), isFalse);
    });
  });
}
