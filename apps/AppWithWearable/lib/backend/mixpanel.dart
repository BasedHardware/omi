import 'package:friend_private/env/env.dart';
import 'package:mixpanel_flutter/mixpanel_flutter.dart';

class MixpanelManager {
  static Mixpanel? _instance;

  static Future<Mixpanel?> init() async {
    if (Env.mixpanelProjectToken == null) return null;
    if (_instance == null) {
      _instance =
          await Mixpanel.init(Env.mixpanelProjectToken!, optOutTrackingDefault: false, trackAutomaticEvents: true);
      _instance?.setLoggingEnabled(false);
    }
    return _instance!;
  }
}
