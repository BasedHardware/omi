import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/runtime.dart';

class AnalyticsManager {
  static final AnalyticsManager _instance = AnalyticsManager._internal();

  factory AnalyticsManager() {
    return _instance;
  }

  AnalyticsManager._internal();

  void setUserAttributes() {
    MixpanelManager().setPeopleValues();
    SafeInit.init(() {
      IntercomManager.instance.setUserAttributes();
    });
  }

  void setUserAttribute(String key, dynamic value) {
    MixpanelManager().setUserProperty(key, value);
    SafeInit.init(() {
      IntercomManager.instance.updateCustomAttributes({key: value});
    });
  }
}
