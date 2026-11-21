import 'package:omi/backend/preferences.dart';

/// The sign-up trial paywall and Pocket's 30-day downsell are offered once per onboarding run.
/// Once the reader has left one, a relaunch (including the one iOS forces after a permission change
/// in Settings) resumes at their step instead of offering it again. Kept per account next to the
/// onboarding resume step and cleared with it when onboarding completes.
abstract final class SignupOffers {
  static String paywallKey(String uid) => 'onboarding/signupPaywall/$uid';
  static String upsellKey(String uid) => 'onboarding/trialUpsell/$uid';

  static const _closed = 'closed';
  static const _purchased = 'purchased';

  /// Shows the sign-up paywall through [open] unless this account already left it. [open] returns
  /// whether the reader bought, or null when no paywall page was shown (nothing is stored then, so the
  /// next launch decides again exactly as the first did). Returns whether the reader bought.
  static Future<bool> paywall(String uid, Future<bool?> Function() open) async {
    final stored = SharedPreferencesUtil().getString(paywallKey(uid));
    if (uid.isNotEmpty && (stored == _closed || stored == _purchased)) return stored == _purchased;
    final purchased = await open();
    if (purchased == null) return false;
    if (uid.isNotEmpty) await SharedPreferencesUtil().saveString(paywallKey(uid), purchased ? _purchased : _closed);
    return purchased;
  }

  /// Shows the downsell through [open] unless this account already left it. [open] returns null when
  /// no sheet was shown (offline, plans not loaded): nothing is stored then.
  static Future<void> upsell(String uid, Future<bool?> Function() open) async {
    if (uid.isNotEmpty && SharedPreferencesUtil().getBool(upsellKey(uid))) return;
    final answer = await open();
    if (answer != null && uid.isNotEmpty) await SharedPreferencesUtil().saveBool(upsellKey(uid), true);
  }

  static void clear(String uid) {
    SharedPreferencesUtil().remove(paywallKey(uid));
    SharedPreferencesUtil().remove(upsellKey(uid));
  }
}
