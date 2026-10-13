import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/onboarding_activation_flow.dart';

// The onboarding ending is A/B by a PostHog flag and fail-closed: off, slow, missing, unknown or
// erroring flag reads all end onboarding the old way (voice introduction = control).

void main() {
  test('flag key is the registered PostHog key', () {
    expect(OnboardingActivationExperiment.enabledFlag, 'onboarding-activation-flow');
  });

  test('no debug override in an ordinary test build', () {
    expect(OnboardingActivationExperiment.debugOverride, isNull);
  });

  group('flag value -> ending', () {
    test('boolean on is treatment, off or missing is control', () {
      expect(OnboardingActivationExperiment.endingForFlagValue(true), OnboardingEnding.activation);
      expect(OnboardingActivationExperiment.endingForFlagValue(false), OnboardingEnding.voiceIntro);
      expect(OnboardingActivationExperiment.endingForFlagValue(null), OnboardingEnding.voiceIntro);
    });

    test('experiment variants: test/treatment/activation are treatment, control is control', () {
      for (final variant in ['test', 'treatment', 'activation', ' Test ']) {
        expect(OnboardingActivationExperiment.endingForFlagValue(variant), OnboardingEnding.activation,
            reason: variant);
      }
      expect(OnboardingActivationExperiment.endingForFlagValue('control'), OnboardingEnding.voiceIntro);
    });

    test('unknown variants and odd values are control', () {
      for (final value in [
        '',
        'variant-b',
        'true',
        1,
        const {'a': 1}
      ]) {
        expect(OnboardingActivationExperiment.endingForFlagValue(value), OnboardingEnding.voiceIntro, reason: '$value');
      }
    });
  });

  group('resolve', () {
    test('flag off -> control, and the variant is not read', () async {
      final keys = <String>[];
      var valueRead = false;
      final ending = await OnboardingActivationExperiment.resolve(
        readEnabled: (key) async {
          keys.add(key);
          return false;
        },
        readValue: (_) async {
          valueRead = true;
          return 'test';
        },
      );
      expect(ending, OnboardingEnding.voiceIntro);
      expect(keys, ['onboarding-activation-flow']);
      expect(valueRead, isFalse);
    });

    test('boolean flag on -> activation', () async {
      expect(
        await OnboardingActivationExperiment.resolve(readEnabled: (_) async => true, readValue: (_) async => true),
        OnboardingEnding.activation,
      );
    });

    test('experiment "control" variant is enabled but still control', () async {
      expect(
        await OnboardingActivationExperiment.resolve(readEnabled: (_) async => true, readValue: (_) async => 'control'),
        OnboardingEnding.voiceIntro,
      );
    });

    test('experiment "test" variant -> activation', () async {
      expect(
        await OnboardingActivationExperiment.resolve(readEnabled: (_) async => true, readValue: (_) async => 'test'),
        OnboardingEnding.activation,
      );
    });

    test('flag read error -> control (fail closed)', () async {
      expect(
        await OnboardingActivationExperiment.resolve(readEnabled: (_) => Future.error(StateError('no sdk'))),
        OnboardingEnding.voiceIntro,
      );
      expect(
        await OnboardingActivationExperiment.resolve(
            readEnabled: (_) async => true, readValue: (_) => Future.error(StateError('no sdk'))),
        OnboardingEnding.voiceIntro,
      );
    });
  });

  group('experiment exposure', () {
    const flag = '\$feature/onboarding-activation-flow';

    test('carries the PostHog variant the arm came from', () async {
      await OnboardingActivationExperiment.resolve(readEnabled: (_) async => true, readValue: (_) async => 'test');
      expect(OnboardingActivationExperiment.exposureProperties(), {flag: 'test'});
      await OnboardingActivationExperiment.resolve(readEnabled: (_) async => true, readValue: (_) async => 'control');
      expect(OnboardingActivationExperiment.exposureProperties(), {flag: 'control'});
    });

    test('readers who fell back to control carry no variant, so they stay out of the analysis', () async {
      await OnboardingActivationExperiment.resolve(readEnabled: (_) async => true, readValue: (_) async => 'test');
      await OnboardingActivationExperiment.resolve(readEnabled: (_) async => false);
      expect(OnboardingActivationExperiment.exposureProperties(), isEmpty);
      await OnboardingActivationExperiment.resolve(readEnabled: (_) => Future.error(StateError('no sdk')));
      expect(OnboardingActivationExperiment.exposureProperties(), isEmpty);
    });
  });

  group('per-account memory', () {
    setUp(() async {
      SharedPreferences.setMockInitialValues({});
      await SharedPreferencesUtil.init();
    });

    test('remembers the started ending per account and forgets it on completion', () {
      expect(OnboardingActivationExperiment.remembered('uid-a'), isNull);
      OnboardingActivationExperiment.remember('uid-a', OnboardingEnding.activation);
      OnboardingActivationExperiment.remember('uid-b', OnboardingEnding.voiceIntro);
      expect(OnboardingActivationExperiment.remembered('uid-a'), OnboardingEnding.activation);
      expect(OnboardingActivationExperiment.remembered('uid-b'), OnboardingEnding.voiceIntro);
      OnboardingActivationExperiment.forget('uid-a');
      expect(OnboardingActivationExperiment.remembered('uid-a'), isNull);
      expect(OnboardingActivationExperiment.remembered('uid-b'), OnboardingEnding.voiceIntro);
    });

    test('no account -> nothing remembered', () {
      OnboardingActivationExperiment.remember('', OnboardingEnding.activation);
      expect(OnboardingActivationExperiment.remembered(''), isNull);
    });
  });
}
