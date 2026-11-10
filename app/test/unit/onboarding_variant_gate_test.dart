import 'package:flutter_test/flutter_test.dart';

import 'package:omi/services/experiments/onboarding_variant_gate.dart';

// Every reader gets Pocket's flow. parse() serves the debug-build override, where an unknown variant
// or a reid payload without an https URL means the native onboarding.

void main() {
  test('readers get pocket without any flag read; the key stays registered', () {
    expect(OnboardingVariantGate.arm, OnboardingArm.pocket);
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
}
