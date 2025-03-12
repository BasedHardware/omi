import 'package:envied/envied.dart';

import 'env.dart';

part 'prod_env.g.dart';

@Envied(allowOptionalFields: true, path: '.env')
final class ProdEnv implements EnvFields {
  ProdEnv();

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _ProdEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  final String? instabugApiKey = _ProdEnv.instabugApiKey;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _ProdEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'API_BASE_URL', obfuscate: true)
  final String? apiBaseUrl = _ProdEnv.apiBaseUrl;

  @override
  @EnviedField(varName: 'GROWTHBOOK_API_KEY', obfuscate: true)
  final String? growthbookApiKey = _ProdEnv.growthbookApiKey;

  @override
  @EnviedField(varName: 'GOOGLE_MAPS_API_KEY', obfuscate: true)
  final String? googleMapsApiKey = _ProdEnv.googleMapsApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_APP_ID', obfuscate: true)
  final String? intercomAppId = _ProdEnv.intercomAppId;

  @override
  @EnviedField(varName: 'INTERCOM_IOS_API_KEY', obfuscate: true)
  final String? intercomIOSApiKey = _ProdEnv.intercomIOSApiKey;

  @override
  @EnviedField(varName: 'INTERCOM_ANDROID_API_KEY', obfuscate: true)
  final String? intercomAndroidApiKey = _ProdEnv.intercomAndroidApiKey;

  @override
  @EnviedField(varName: 'POSTHOG_API_KEY', obfuscate: true)
  final String? posthogApiKey = _ProdEnv.posthogApiKey;

  // Firebase Configuration
  @override
  @EnviedField(varName: 'FIREBASE_ANDROID_API_KEY', obfuscate: true)
  final String? firebaseAndroidApiKey = _ProdEnv.firebaseAndroidApiKey;

  @override
  @EnviedField(varName: 'FIREBASE_ANDROID_APP_ID', obfuscate: true)
  final String? firebaseAndroidAppId = _ProdEnv.firebaseAndroidAppId;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_API_KEY', obfuscate: true)
  final String? firebaseIosApiKey = _ProdEnv.firebaseIosApiKey;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_APP_ID', obfuscate: true)
  final String? firebaseIosAppId = _ProdEnv.firebaseIosAppId;

  @override
  @EnviedField(varName: 'FIREBASE_MESSAGING_SENDER_ID', obfuscate: true)
  final String? firebaseMessagingSenderId = _ProdEnv.firebaseMessagingSenderId;

  @override
  @EnviedField(varName: 'FIREBASE_PROJECT_ID', obfuscate: true)
  final String? firebaseProjectId = _ProdEnv.firebaseProjectId;

  @override
  @EnviedField(varName: 'FIREBASE_STORAGE_BUCKET', obfuscate: true)
  final String? firebaseStorageBucket = _ProdEnv.firebaseStorageBucket;

  @override
  @EnviedField(varName: 'FIREBASE_ANDROID_CLIENT_ID', obfuscate: true)
  final String? firebaseAndroidClientId = _ProdEnv.firebaseAndroidClientId;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_CLIENT_ID', obfuscate: true)
  final String? firebaseIosClientId = _ProdEnv.firebaseIosClientId;

  @override
  @EnviedField(varName: 'FIREBASE_IOS_BUNDLE_ID', obfuscate: true)
  final String? firebaseIosBundleId = _ProdEnv.firebaseIosBundleId;
}
