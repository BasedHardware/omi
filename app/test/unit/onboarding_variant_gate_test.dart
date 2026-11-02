import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/onboarding_variant_gate.dart';

// The onboarding variant gate is fail-closed: off, slow, erroring, an unknown variant, or a reid
// payload without an https URL all mean the native onboarding exactly as before.

void main() {
  setUp(OnboardingVariantGate.resetForTesting);

  test('flag key is the registered PostHog key', () {
    expect(OnboardingVariantGate.enabledFlag, 'onboarding-variant');
    expect(OnboardingVariantGate.debugOverride, isNull);
  });

  test('parse: yinka is native, reid needs an https URL from a map or a JSON string', () {
    expect(OnboardingVariantGate.parse(variant: 'yinka'), OnboardingArm.yinka);
    expect(OnboardingVariantGate.parse(variant: ' yinka ', payload: 'ignored'), OnboardingArm.yinka);
    expect(OnboardingVariantGate.parse(variant: 'pocket'), OnboardingArm.pocket);
    expect(OnboardingVariantGate.parse(variant: 'pocket', payload: 'ignored').variant, OnboardingVariant.pocket);
    expect(OnboardingVariantGate.parse(variant: 'reid', payload: {'url': 'https://x.example/onboarding'}).variant,
        OnboardingVariant.reid);
    expect(OnboardingVariantGate.parse(variant: 'reid', payload: {'url': 'https://x.example/onboarding'}).webUrl,
        Uri.parse('https://x.example/onboarding'));
    expect(OnboardingVariantGate.parse(variant: 'reid', payload: '{"url":"https://x.example/o"}').webUrl,
        Uri.parse('https://x.example/o'));
    expect(OnboardingVariantGate.parse(variant: 'reid', payload: {'url': 'http://x.example'}), OnboardingArm.control);
    expect(OnboardingVariantGate.parse(variant: 'reid', payload: {}), OnboardingArm.control);
    expect(OnboardingVariantGate.parse(variant: 'reid', payload: 'garbage'), OnboardingArm.control);
    expect(
        OnboardingVariantGate.parse(variant: 'control', payload: {'url': 'https://x.example'}), OnboardingArm.control);
    expect(OnboardingVariantGate.parse(variant: 'something-else'), OnboardingArm.control);
    expect(OnboardingVariantGate.parse(variant: null), OnboardingArm.control);
  });

  test('control or an unread flag -> native, without reading the payload', () async {
    var payloadReads = 0;
    for (final variant in [null, 'control', 'unknown']) {
      final arm = await OnboardingVariantGate.resolve(
        settledIdentity: () => 'u',
        reload: () async => true,
        readVariant: (_) async => variant,
        readPayload: (_) async {
          payloadReads++;
          return {'url': 'https://x.example'};
        },
      );
      expect(arm, OnboardingArm.control, reason: 'variant $variant');
    }
    expect(payloadReads, 0);
  });

  test('yinka -> the native flow, without reading the payload', () async {
    var payloadReads = 0;
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => 'u',
      reload: () async => true,
      readVariant: (_) async => 'yinka',
      readPayload: (_) async {
        payloadReads++;
        return null;
      },
    );
    expect(arm, OnboardingArm.yinka);
    expect(payloadReads, 0);
  });

  test('reid -> the payload URL', () async {
    final keys = <String>[];
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => 'u',
      reload: () async => true,
      readVariant: (key) async {
        keys.add(key);
        return 'reid';
      },
      readPayload: (_) async => {'url': 'https://x.example/onboarding'},
    );
    expect(arm.variant, OnboardingVariant.reid);
    expect(arm.webUrl, Uri.parse('https://x.example/onboarding'));
    expect(keys, ['onboarding-variant']);
  });

  test('flag read error -> native (fail closed)', () async {
    expect(
        await OnboardingVariantGate.resolve(
            settledIdentity: () => 'u',
            reload: () async => true,
            readVariant: (_) => Future.error(StateError('no sdk'))),
        OnboardingArm.control);
  });

  test('waits for the identity to settle and reloads flags before the first read', () async {
    final order = <String>[];
    var polls = 0;
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => ++polls < 4 ? null : 'u',
      reload: () async {
        order.add('reload');
        return true;
      },
      readVariant: (_) async {
        order.add('read');
        return 'yinka';
      },
    );
    expect(arm, OnboardingArm.yinka);
    expect(order, ['reload', 'read']);
    expect(polls, greaterThanOrEqualTo(4));
  });

  test('no identity within the wait -> native, without reading anything', () async {
    var reads = 0;
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => null,
      identityWait: const Duration(milliseconds: 200),
      reload: () async {
        reads++;
        return true;
      },
      readVariant: (_) async {
        reads++;
        return 'yinka';
      },
    );
    expect(arm, OnboardingArm.control);
    expect(reads, 0);
  });

  test('a warm-up started on the consent screen answers the tap without restarting the wait', () async {
    var polls = 0;
    var reads = 0;
    OnboardingVariantGate.warm(
      settledIdentity: () => ++polls < 6 ? null : 'u',
      reload: () async => true,
      readVariant: (_) async {
        reads++;
        return 'yinka';
      },
    );
    final arm = await OnboardingVariantGate.resolve(settledIdentity: () => null, identityWait: Duration.zero);
    expect(arm, OnboardingArm.yinka);
    expect(reads, 1);
    // The warm-up is consumed: the next resolve is a cold read again.
    expect(await OnboardingVariantGate.resolve(settledIdentity: () => null, identityWait: Duration.zero),
        OnboardingArm.control);
  });

  test('a warm-up for account A is discarded when the account changes before the tap', () async {
    var epoch = 1;
    var warmReads = 0;
    OnboardingVariantGate.warm(
      settledIdentity: () => 'a',
      reload: () async => true,
      identityEpoch: () => epoch,
      readVariant: (_) async {
        warmReads++;
        return 'yinka';
      },
    );
    epoch = 2; // "use a different account": the analytics identity moved on
    var coldReads = 0;
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => 'b',
      reload: () async => true,
      identityEpoch: () => epoch,
      readVariant: (_) async {
        coldReads++;
        return 'control';
      },
    );
    expect(arm, OnboardingArm.control, reason: 'B gets its own (control) answer, never A\'s warmed arm');
    expect(coldReads, 1);
    expect(warmReads, 1);
  });

  test('an account change while a read is in flight yields native', () async {
    var epoch = 1;
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => 'a',
      reload: () async => true,
      identityEpoch: () => epoch,
      readVariant: (_) async {
        epoch = 2;
        return 'yinka';
      },
    );
    expect(arm, OnboardingArm.control);
  });

  test('a failed or timed-out flag reload yields native even when the stale flag says on', () async {
    var reads = 0;
    final arm = await OnboardingVariantGate.resolve(
      settledIdentity: () => 'u',
      reload: () async => false,
      readVariant: (_) async {
        reads++;
        return 'yinka';
      },
    );
    expect(arm, OnboardingArm.control);
    expect(reads, 0, reason: 'nothing is read on top of stale flags');
    expect(
      await OnboardingVariantGate.resolve(
        settledIdentity: () => 'u',
        reload: () => Future.error(TimeoutException('flags')),
        readVariant: (_) async => 'yinka',
      ),
      OnboardingArm.control,
    );
  });
}
