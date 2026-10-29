import 'dart:convert';

import 'package:omi/backend/preferences.dart';
import 'package:omi/services/experiments/onboarding_variant_gate.dart';

/// How the reader answered the sign-up trial paywall.
enum SignupPaywallAnswer {
  closed('closed'),
  purchased('purchased');

  const SignupPaywallAnswer(this.wireName);

  final String wireName;
}

/// What a relaunch mid-onboarding must not decide again, per account on this phone. Each flow's own
/// resume key (wrapper, pocket, yinka) keeps the step the reader was on; this keeps what was settled
/// before the steps: the `onboarding-variant` arm the account was first given, and its answer to the
/// sign-up trial paywall and to pocket's 30-day downsell.
///
/// The arm is sticky: a relaunch re-enters it whatever the flag reads this time (a slow read that
/// falls back to control, or a changed split), and the debug arm override only applies to a first
/// resolution. Cleared when onboarding completes.
abstract final class OnboardingResumeState {
  static String armKey(String uid) => 'onboarding/arm/$uid';
  static String signupPaywallKey(String uid) => 'onboarding/signupPaywall/$uid';
  static String trialUpsellKey(String uid) => 'onboarding/trialUpsell/$uid';

  /// The arm [uid] was first given, or null before its first resolution.
  static OnboardingArm? arm(String uid) {
    if (uid.isEmpty) return null;
    final raw = SharedPreferencesUtil().getString(armKey(uid));
    if (raw.isEmpty) return null;
    try {
      final value = jsonDecode(raw);
      if (value is! Map || value['variant'] is! String) return null;
      return OnboardingVariantGate.parse(variant: value['variant'] as String, payload: {'url': value['url']});
    } on FormatException {
      return null;
    }
  }

  static Future<void> saveArm(String uid, OnboardingArm arm) async {
    if (uid.isEmpty) return;
    await SharedPreferencesUtil().saveString(
      armKey(uid),
      jsonEncode({'variant': arm.variant.wireName, if (arm.webUrl != null) 'url': arm.webUrl.toString()}),
    );
  }

  /// The answer [uid] gave the sign-up trial paywall, or null when it was never answered (a reader
  /// who left the app with the paywall open sees it again).
  static SignupPaywallAnswer? signupPaywall(String uid) {
    if (uid.isEmpty) return null;
    final raw = SharedPreferencesUtil().getString(signupPaywallKey(uid));
    for (final answer in SignupPaywallAnswer.values) {
      if (answer.wireName == raw) return answer;
    }
    return null;
  }

  static Future<void> saveSignupPaywall(String uid, SignupPaywallAnswer answer) async {
    if (uid.isEmpty) return;
    await SharedPreferencesUtil().saveString(signupPaywallKey(uid), answer.wireName);
  }

  /// Pocket's 30-day downsell had its one chance.
  static bool trialUpsellDone(String uid) => uid.isNotEmpty && SharedPreferencesUtil().getBool(trialUpsellKey(uid));

  static Future<void> saveTrialUpsellDone(String uid) async {
    if (uid.isEmpty) return;
    await SharedPreferencesUtil().saveBool(trialUpsellKey(uid), true);
  }

  /// Onboarding is done: nothing here is read again.
  static Future<void> clear(String uid) async {
    if (uid.isEmpty) return;
    await SharedPreferencesUtil().remove(armKey(uid));
    await SharedPreferencesUtil().remove(signupPaywallKey(uid));
    await SharedPreferencesUtil().remove(trialUpsellKey(uid));
  }
}
