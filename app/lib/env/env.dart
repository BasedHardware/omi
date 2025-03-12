import 'package:friend_private/env/dev_env.dart';

abstract class Env {
  static late final EnvFields _instance;

  static void init([EnvFields? instance]) {
    _instance = instance ?? DevEnv() as EnvFields;
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get instabugApiKey => _instance.instabugApiKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  static String? get apiBaseUrl => _instance.apiBaseUrl;

  // static String? get apiBaseUrl => 'https://backend-dt5lrfkkoa-uc.a.run.app/';
  // // static String? get apiBaseUrl => 'https://camel-lucky-reliably.ngrok-free.app/';
  // static String? get apiBaseUrl => 'https://mutual-fun-boar.ngrok-free.app/';

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get posthogApiKey => _instance.posthogApiKey;

  // Firebase Configuration
  static String? get firebaseAndroidApiKey => _instance.firebaseAndroidApiKey;
  static String? get firebaseAndroidAppId => _instance.firebaseAndroidAppId;
  static String? get firebaseIosApiKey => _instance.firebaseIosApiKey;
  static String? get firebaseIosAppId => _instance.firebaseIosAppId;
  static String? get firebaseMessagingSenderId => _instance.firebaseMessagingSenderId;
  static String? get firebaseProjectId => _instance.firebaseProjectId;
  static String? get firebaseStorageBucket => _instance.firebaseStorageBucket;
  static String? get firebaseAndroidClientId => _instance.firebaseAndroidClientId;
  static String? get firebaseIosClientId => _instance.firebaseIosClientId;
  static String? get firebaseIosBundleId => _instance.firebaseIosBundleId;
}

abstract class EnvFields {
  String? get openAIAPIKey;

  String? get instabugApiKey;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  String? get posthogApiKey;

  // Firebase Configuration
  String? get firebaseAndroidApiKey;
  String? get firebaseAndroidAppId;
  String? get firebaseIosApiKey;
  String? get firebaseIosAppId;
  String? get firebaseMessagingSenderId;
  String? get firebaseProjectId;
  String? get firebaseStorageBucket;
  String? get firebaseAndroidClientId;
  String? get firebaseIosClientId;
  String? get firebaseIosBundleId;
}
