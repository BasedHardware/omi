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

  // static String? get apiBaseUrl => 'https://based-hardware-development--backened-dev-api.modal.run/';
  // static String? get apiBaseUrl => 'https://camel-lucky-reliably.ngrok-free.app/';
  // static String? get apiBaseUrl => 'https://mutual-fun-boar.ngrok-free.app/';

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;

  static String? get intercomAppId => _instance.intercomAppId;

  static String? get intercomIOSApiKey => _instance.intercomIOSApiKey;

  static String? get intercomAndroidApiKey => _instance.intercomAndroidApiKey;
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
}
