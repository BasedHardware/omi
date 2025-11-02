import 'package:omi/env/dev_env.dart';

abstract class Env {
  static late final EnvFields _instance;

  static void init([EnvFields? instance]) {
    _instance = instance ?? DevEnv() as EnvFields;
  }

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  // static String? get apiBaseUrl => 'https://omi-backend.ngrok.app/';
  static String? get apiBaseUrl => _instance.apiBaseUrl;

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;

  static String? get googleClientId => _instance.googleClientId;

  static String? get googleClientSecret => _instance.googleClientSecret;

  static String? get todoistClientId => _instance.todoistClientId;

  static String? get todoistClientSecret => _instance.todoistClientSecret;

  static String? get todoistVerificationToken => _instance.todoistVerificationToken;

  static String? get asanaClientId => _instance.asanaClientId;

  static String? get asanaClientSecret => _instance.asanaClientSecret;

  static String? get googleTasksClientId => _instance.googleTasksClientId;

  static String? get googleTasksClientSecret => _instance.googleTasksClientSecret;

  static String? get clickupClientId => _instance.clickupClientId;

  static String? get clickupClientSecret => _instance.clickupClientSecret;
}

abstract class EnvFields {
  String? get openAIAPIKey;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;

  String? get intercomAppId;

  String? get intercomIOSApiKey;

  String? get intercomAndroidApiKey;

  String? get googleClientId;

  String? get googleClientSecret;

  String? get todoistClientId;

  String? get todoistClientSecret;

  String? get todoistVerificationToken;

  String? get asanaClientId;

  String? get asanaClientSecret;

  String? get googleTasksClientId;

  String? get googleTasksClientSecret;

  String? get clickupClientId;

  String? get clickupClientSecret;
}
