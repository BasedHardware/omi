import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/onboarding_resume_state.dart';
import 'package:omi/services/experiments/onboarding_variant_gate.dart';

// What a relaunch mid-onboarding must not decide again is kept per account, survives a cold start
// (it lives in the phone's preferences), and is gone once onboarding completes.

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('nothing is stored before the first resolution or answer', () {
    expect(OnboardingResumeState.arm('u1'), isNull);
    expect(OnboardingResumeState.signupPaywall('u1'), isNull);
    expect(OnboardingResumeState.trialUpsellDone('u1'), isFalse);
  });

  test('the arm round-trips, reid with its page', () async {
    final reid = OnboardingArm(OnboardingVariant.reid, webUrl: Uri.parse('https://x.example/onboarding'));
    for (final arm in [OnboardingArm.control, OnboardingArm.pocket, OnboardingArm.yinka, reid]) {
      await OnboardingResumeState.saveArm('u1', arm);
      expect(OnboardingResumeState.arm('u1'), arm);
    }
  });

  test('a stored arm that does not parse is no arm, so the flag decides', () async {
    for (final raw in ['pocket', '{"variant": 3}', '[]', '{']) {
      await SharedPreferencesUtil().saveString(OnboardingResumeState.armKey('u1'), raw);
      expect(OnboardingResumeState.arm('u1'), isNull, reason: raw);
    }
  });

  test('answers are per account, and an empty uid never reads or writes', () async {
    await OnboardingResumeState.saveArm('u1', OnboardingArm.pocket);
    await OnboardingResumeState.saveSignupPaywall('u1', SignupPaywallAnswer.purchased);
    await OnboardingResumeState.saveTrialUpsellDone('u1');
    expect(OnboardingResumeState.arm('u2'), isNull);
    expect(OnboardingResumeState.signupPaywall('u2'), isNull);
    expect(OnboardingResumeState.trialUpsellDone('u2'), isFalse);

    await OnboardingResumeState.saveArm('', OnboardingArm.yinka);
    await OnboardingResumeState.saveSignupPaywall('', SignupPaywallAnswer.closed);
    await OnboardingResumeState.saveTrialUpsellDone('');
    expect(OnboardingResumeState.arm(''), isNull);
    expect(OnboardingResumeState.signupPaywall(''), isNull);
    expect(OnboardingResumeState.trialUpsellDone(''), isFalse);
    expect(SharedPreferencesUtil().getString(OnboardingResumeState.armKey('')), isEmpty);
  });

  test('a cold start reads what the last session stored', () async {
    await OnboardingResumeState.saveArm('u1', OnboardingArm.pocket);
    await OnboardingResumeState.saveSignupPaywall('u1', SignupPaywallAnswer.closed);
    await OnboardingResumeState.saveTrialUpsellDone('u1');
    final stored = (await SharedPreferences.getInstance()).getKeys();
    SharedPreferences.setMockInitialValues({
      for (final key in stored) key: (await SharedPreferences.getInstance()).get(key)!,
    });
    await SharedPreferencesUtil.init();

    expect(OnboardingResumeState.arm('u1'), OnboardingArm.pocket);
    expect(OnboardingResumeState.signupPaywall('u1'), SignupPaywallAnswer.closed);
    expect(OnboardingResumeState.trialUpsellDone('u1'), isTrue);
  });

  test('completion clears the account and leaves others alone', () async {
    for (final uid in ['u1', 'u2']) {
      await OnboardingResumeState.saveArm(uid, OnboardingArm.pocket);
      await OnboardingResumeState.saveSignupPaywall(uid, SignupPaywallAnswer.closed);
      await OnboardingResumeState.saveTrialUpsellDone(uid);
    }
    await OnboardingResumeState.clear('u1');
    expect(OnboardingResumeState.arm('u1'), isNull);
    expect(OnboardingResumeState.signupPaywall('u1'), isNull);
    expect(OnboardingResumeState.trialUpsellDone('u1'), isFalse);
    expect(OnboardingResumeState.arm('u2'), OnboardingArm.pocket);
    expect(OnboardingResumeState.signupPaywall('u2'), SignupPaywallAnswer.closed);
    expect(OnboardingResumeState.trialUpsellDone('u2'), isTrue);
  });
}
