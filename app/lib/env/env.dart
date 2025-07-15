import 'package:omi/env/dev_env.dart';

abstract class Env {
  static late final EnvFields _instance;

  static void init([EnvFields? instance]) {
    _instance = instance ?? DevEnv() as EnvFields;
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get instabugApiKey => _instance.instabugApiKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  static String? get apiBaseUrl => _instance.apiBaseUrl;

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get posthogApiKey => _instance.posthogApiKey;

  static String? get googleClientId => _instance.googleClientId;

  static String? get googleClientSecret => _instance.googleClientSecret;
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

  String? get googleClientId;

  String? get googleClientSecret;
}
