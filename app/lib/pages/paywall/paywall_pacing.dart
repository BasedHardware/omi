import 'package:omi/backend/preferences.dart';

/// When this account last saw a paywall. Every paywall surface records itself when it appears, so
/// an automatic offer (`ValueMomentPaywall`) keeps [window] away from the last paywall, whatever
/// placement showed it.
abstract final class PaywallPacing {
  static const window = Duration(hours: 72);

  static String get _key => 'paywallLastShownMs:${SharedPreferencesUtil().uid}';

  static void markShown({DateTime? now}) =>
      SharedPreferencesUtil().saveInt(_key, (now ?? DateTime.now()).millisecondsSinceEpoch);

  static bool shownRecently({DateTime? now}) {
    final last = SharedPreferencesUtil().getInt(_key);
    if (last <= 0) return false;
    return (now ?? DateTime.now()).difference(DateTime.fromMillisecondsSinceEpoch(last)) < window;
  }
}
