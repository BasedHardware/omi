import 'package:friend_private/utils/analytics/intercom.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class AnalyticsManager {
  static final AnalyticsManager _instance = AnalyticsManager._internal();

  factory AnalyticsManager() {
    return _instance;
  }

  AnalyticsManager._internal();

  void setUserAttributes() {
    MixpanelManager().setPeopleValues();
    IntercomManager.instance.setUserAttributes();
  }

  void setUserAttribute(String key, dynamic value) {
    MixpanelManager().setUserProperty(key, value);
    IntercomManager.instance.updateCustomAttributes({key: value});
  }
}
