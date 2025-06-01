import 'dart:io';

import 'package:omi/utils/platform/platform_manager.dart';

class AnalyticsManager {
  static final AnalyticsManager _instance = AnalyticsManager._internal();

  factory AnalyticsManager() {
    return _instance;
  }

  AnalyticsManager._internal();

  void setUserAttributes() {
    PlatformManager.instance.mixpanel.setPeopleValues();
    PlatformManager.instance.intercom.setUserAttributes();
  }

  void setUserAttribute(String key, dynamic value) {
    PlatformManager.instance.mixpanel.setUserProperty(key, value);
    PlatformManager.instance.intercom.updateCustomAttributes({key: value});
  }

  void trackEvent(String eventName, {Map<String, dynamic>? properties}) {
    PlatformManager.instance.mixpanel.track(eventName, properties: properties);
    PlatformManager.instance.intercom.logEvent(eventName, metaData: properties);
  }
}
