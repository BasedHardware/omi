// A confirmed-subscription quiet that already delivered audio is healthy listening, not a lapsed
// link (the pendant sends audio only while there is sound); a quiet with no audio this generation
// proves nothing. Pins the state mapping of #20378: Listening needs a confirmed subscription PLUS
// audio on the current connection generation.
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
    int lastAudioAtMs = 0,
    String generation = 'gen',
  }) =>
      CaptureIngressHealth(
        phase: phase,
        generation: generation,
        reason: 'test',
        validUntilMs: validUntilMs,
        subscriptionConfirmed: subscriptionConfirmed,
        unverifiedSinceMs: 0,
        lastAudioAtMs: lastAudioAtMs,
      );

  group('CaptureIngressHealth.verifiedAt', () {
    test('a flowing lease within its lifetime verifies', () {
      final valid = now.millisecondsSinceEpoch + 30000;
      expect(health(phase: 'flowing', validUntilMs: valid, lastAudioAtMs: now.millisecondsSinceEpoch).verifiedAt(now),
          isTrue);
    });

    test('a confirmed-subscription quiet verifies once audio arrived in this generation', () {
      // Native quiet (fresh_subscription_quiet, budget_spent_quiet) has no audio lease:
      // the last audio's 30 s window is what expired, so valid_until_ms is in the past
      // (or 0). Silence after sound is not a lapse.
      final heard = now.millisecondsSinceEpoch - 60000;
      expect(
          health(phase: 'quiet', lastAudioAtMs: heard, validUntilMs: now.millisecondsSinceEpoch - 30000)
              .verifiedAt(now),
          isTrue);
      expect(health(phase: 'quiet', lastAudioAtMs: heard, validUntilMs: 0).verifiedAt(now), isTrue);
    });

    test('a fresh quiet with no audio this generation does not verify (#20378)', () {
      // fresh_subscription_quiet with hadAudio == false: the subscription is confirmed
      // but nothing this generation ever proved it delivers. That is the wait the
      // island grace and the unheard notice exist for, not Listening.
      expect(health(phase: 'quiet', lastAudioAtMs: 0, validUntilMs: 0).verifiedAt(now), isFalse);
    });

    test('a new generation resets the proof: its quiet starts unverified', () {
      // Audio arrived on generation one, then the link reconnected. The new
      // generation's snapshot has no audio of its own, so its quiet — and even a
      // fresh unverified frame — claims nothing until audio returns.
      final heard = now.millisecondsSinceEpoch - 60000;
      expect(
          health(phase: 'quiet', generation: 'gen-1', lastAudioAtMs: heard, validUntilMs: 0).verifiedAt(now), isTrue);
      expect(health(phase: 'quiet', generation: 'gen-2', lastAudioAtMs: 0, validUntilMs: 0).verifiedAt(now), isFalse);
      // budget_spent_quiet follows the same rule: a spent budget is healthy only
      // when this generation's link has delivered audio.
      expect(health(phase: 'quiet', generation: 'gen-2', lastAudioAtMs: 0, validUntilMs: 0).verifiedAt(now), isFalse);
    });

    test('quiet without a confirmed subscription does not verify', () {
      expect(
          health(phase: 'quiet', subscriptionConfirmed: false, lastAudioAtMs: now.millisecondsSinceEpoch)
              .verifiedAt(now),
          isFalse);
    });

    test('a wait, a repair, a reconnect and an exhausted recovery do not verify', () {
      for (final phase in ['inactive', 'unverified', 'repairing', 'reconnecting', 'actionRequired']) {
        expect(
            health(
              phase: phase,
              validUntilMs: now.millisecondsSinceEpoch + 30000,
              lastAudioAtMs: now.millisecondsSinceEpoch,
            ).verifiedAt(now),
            isFalse,
            reason: phase);
      }
    });

    test('an expired flowing lease does not verify until native settles it', () {
      expect(
        health(
          phase: 'flowing',
          validUntilMs: now.millisecondsSinceEpoch - 1,
          lastAudioAtMs: now.millisecondsSinceEpoch - 31000,
        ).verifiedAt(now),
        isFalse,
      );
    });

    test('parses the native snapshot shape', () {
      final parsed = CaptureIngressHealth.parse(jsonEncode({
        'phase': 'quiet',
        'generation': 'gen',
        'reason': 'fresh_subscription_quiet',
        'last_audio_at_ms': now.millisecondsSinceEpoch - 60000,
        'valid_until_ms': 0,
        'subscription_confirmed': true,
        'unverified_since_ms': 0,
      }));
      expect(parsed, isNotNull);
      expect(parsed!.verifiedAt(now), isTrue);
      expect(parsed.actionable, isFalse);
      final fresh = CaptureIngressHealth.parse(jsonEncode({
        'phase': 'quiet',
        'generation': 'gen',
        'reason': 'fresh_subscription_quiet',
        'last_audio_at_ms': 0,
        'valid_until_ms': 0,
        'subscription_confirmed': true,
        'unverified_since_ms': 0,
      }));
      expect(fresh!.verifiedAt(now), isFalse, reason: 'no audio this generation is not Listening');
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
