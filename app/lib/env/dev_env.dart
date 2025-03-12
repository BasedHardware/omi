import 'package:envied/envied.dart';

import 'env.dart';

part 'dev_env.g.dart';

@Envied(allowOptionalFields: true, path: '.dev.env')
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _DevEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  final String? instabugApiKey = _DevEnv.instabugApiKey;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _DevEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'API_BASE_URL', obfuscate: true)
  final String? apiBaseUrl = _DevEnv.apiBaseUrl;

  @override
  @EnviedField(varName: 'GROWTHBOOK_API_KEY', obfuscate: true)
  final String? growthbookApiKey = _DevEnv.growthbookApiKey;

  @override
  @EnviedField(varName: 'GOOGLE_MAPS_API_KEY', obfuscate: true)
  final String? googleMapsApiKey = _DevEnv.googleMapsApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_APP_ID', obfuscate: true)
  final String? intercomAppId = _DevEnv.intercomAppId;

  @override
  @EnviedField(varName: 'INTERCOM_IOS_API_KEY', obfuscate: true)
  final String? intercomIOSApiKey = _DevEnv.intercomIOSApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_ANDROID_API_KEY', obfuscate: true)
  final String? intercomAndroidApiKey = _DevEnv.intercomAndroidApiKey;

  @override
  @EnviedField(varName: 'POSTHOG_API_KEY', obfuscate: true)
  final String? posthogApiKey = _DevEnv.posthogApiKey;

  // Firebase Configuration
  @override
  @EnviedField(varName: 'FIREBASE_ANDROID_API_KEY', obfuscate: true)
  final String? firebaseAndroidApiKey = _DevEnv.firebaseAndroidApiKey;

  @override
  @EnviedField(varName: 'FIREBASE_ANDROID_APP_ID', obfuscate: true)
  final String? firebaseAndroidAppId = _DevEnv.firebaseAndroidAppId;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_API_KEY', obfuscate: true)
  final String? firebaseIosApiKey = _DevEnv.firebaseIosApiKey;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_APP_ID', obfuscate: true)
  final String? firebaseIosAppId = _DevEnv.firebaseIosAppId;

  @override
  @EnviedField(varName: 'FIREBASE_MESSAGING_SENDER_ID', obfuscate: true)
  final String? firebaseMessagingSenderId = _DevEnv.firebaseMessagingSenderId;

  @override
  @EnviedField(varName: 'FIREBASE_PROJECT_ID', obfuscate: true)
  final String? firebaseProjectId = _DevEnv.firebaseProjectId;

  @override
  @EnviedField(varName: 'FIREBASE_STORAGE_BUCKET', obfuscate: true)
  final String? firebaseStorageBucket = _DevEnv.firebaseStorageBucket;

  @override
  @EnviedField(varName: 'FIREBASE_ANDROID_CLIENT_ID', obfuscate: true)
  final String? firebaseAndroidClientId = _DevEnv.firebaseAndroidClientId;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_CLIENT_ID', obfuscate: true)
  final String? firebaseIosClientId = _DevEnv.firebaseIosClientId;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_BUNDLE_ID', obfuscate: true)
  final String? firebaseIosBundleId = _DevEnv.firebaseIosBundleId;
}
