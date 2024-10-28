import 'dart:async';

import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/env/env.dart';
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
    await intercom.initialize(
      Env.intercomAppId!,
      iosApiKey: Env.intercomIOSApiKey,
      androidApiKey: Env.intercomAndroidApiKey,
    );
  }

  Future displayChargingArticle(String device) async {
    if (device == 'Omi DevKit 2') {
      return await intercom.displayArticle('10003257-how-to-charge-devkit2');
    } else {
      return await intercom.displayArticle('9907475-how-to-charge-the-device');
    }
  }

  Future displayFirmwareUpdateArticle() async {
    return await intercom.displayArticle('9918118-updating-your-friend-device-firmware');
  }

  Future logEvent(String eventName, {Map<String, dynamic>? metaData}) async {
    return await intercom.logEvent(eventName, metaData);
  }

  Future updateCustomAttributes(Map<String, dynamic> attributes) async {
    return await intercom.updateUser(customAttributes: attributes);
  }

  Future updateUser(String? email, String? name, String? uid) async {
    return await intercom.updateUser(
      email: email,
      name: name,
      userId: uid,
    );
  }

  Future<void> setUserAttributes() async {
    await updateCustomAttributes({
      'Notifications Enabled': _preferences.notificationsEnabled,
      'Location Enabled': _preferences.locationEnabled,
      'Apps Enabled Count': _preferences.enabledAppsCount,
      'Apps Integrations Enabled Count': _preferences.enabledAppsIntegrationsCount,
      'Speaker Profile': _preferences.hasSpeakerProfile,
      'Calendar Enabled': _preferences.calendarEnabled,
      'Recordings Language': _preferences.recordingsLanguage,
      'Authorized Storing Recordings': _preferences.permissionStoreRecordingsEnabled,
      'GCP Integration Set': _preferences.gcpCredentials.isNotEmpty && _preferences.gcpBucketName.isNotEmpty,
    });
  }
}
