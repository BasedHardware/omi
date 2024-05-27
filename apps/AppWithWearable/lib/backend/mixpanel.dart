import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
import 'package:mixpanel_flutter/mixpanel_flutter.dart';

class MixpanelManager {
  static final MixpanelManager _instance = MixpanelManager._internal();
  static Mixpanel? _mixpanel;
  static final SharedPreferencesUtil _preferences = SharedPreferencesUtil();

  static Future<void> init() async {
    if (Env.mixpanelProjectToken == null) return;
    if (_mixpanel == null) {
      _mixpanel =
          await Mixpanel.init(Env.mixpanelProjectToken!, optOutTrackingDefault: false, trackAutomaticEvents: true);
      _mixpanel?.setLoggingEnabled(false);
      _instance.identify();
    }
  }

  factory MixpanelManager() {
    return _instance;
  }

  MixpanelManager._internal();

  void optInTracking() => _mixpanel?.optInTracking();

  void optOutTracking() => _mixpanel?.optOutTracking();

  void identify() => _mixpanel?.identify(_preferences.uid);

  void track(String eventName, {Map<String, dynamic>? properties}) =>
      _mixpanel?.track(eventName, properties: properties);

  void logout() => _mixpanel?.reset();
}
