import 'dart:async';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:intercom_flutter/intercom_flutter.dart';

class IntercomManager {
  static final IntercomManager _instance = IntercomManager._internal();
  static IntercomManager get instance => _instance;
  static final SharedPreferencesUtil _preferences = SharedPreferencesUtil();

  IntercomManager._internal();

  Intercom get intercom => Intercom.instance;

  factory IntercomManager() {
    return _instance;
  }

  Future<void> initIntercom() async {
    if (Env.intercomAppId == null) return;
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.initialize(
        Env.intercomAppId!,
        iosApiKey: Env.intercomIOSApiKey,
        androidApiKey: Env.intercomAndroidApiKey,
      ),
    );
  }

  Future displayChargingArticle(String device) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () async {
        if (device == 'Omi DevKit 2') {
          return await intercom.displayArticle('10003257-how-to-charge-devkit2');
        } else if(device == 'Omi') {
          return await intercom.displayArticle('12123047-how-to-charge-omi');
        } else {
          return await intercom.displayArticle('9907475-how-to-charge-the-device');
        }
      },
    );
  }

  Future loginIdentifiedUser(String uid) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.loginIdentifiedUser(userId: uid),
    );
  }

  Future loginUnidentifiedUser() async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.loginUnidentifiedUser(),
    );
  }

  Future displayEarnMoneyArticle() async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.displayArticle('10401566-build-publish-and-earn-with-omi-apps'),
    );
  }

  Future displayFirmwareUpdateArticle() async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.displayArticle('9995941-updating-your-devkit2-firmware'),
    );
  }

  Future logEvent(String eventName, {Map<String, dynamic>? metaData}) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.logEvent(eventName, metaData),
    );
  }

  Future updateCustomAttributes(Map<String, dynamic> attributes) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.updateUser(customAttributes: attributes),
    );
  }

  Future updateUser(String? email, String? name, String? uid) async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => intercom.updateUser(
        email: email,
        name: name,
        userId: uid,
      ),
    );
  }

  Future<void> setUserAttributes() async {
    return PlatformService.executeIfSupportedAsync(
      PlatformService.isIntercomSupported,
      () => updateCustomAttributes({
        'Notifications Enabled': _preferences.notificationsEnabled,
        'Location Enabled': _preferences.locationEnabled,
        'Apps Enabled Count': _preferences.enabledAppsCount,
        'Apps Integrations Enabled Count': _preferences.enabledAppsIntegrationsCount,
        'Speaker Profile': _preferences.hasSpeakerProfile,
        'Calendar Enabled': _preferences.calendarEnabled,
        'Primary Language': _preferences.userPrimaryLanguage,
        'Authorized Storing Recordings': _preferences.permissionStoreRecordingsEnabled,
      }),
    );
  }
}
