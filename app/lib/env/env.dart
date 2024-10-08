import 'package:friend_private/env/dev_env.dart';
import 'package:friend_private/services/remote_config_service.dart';

abstract class Env {
  static late final EnvFields _instance;

  static void init([EnvFields? instance]) {
    _instance = instance ?? DevEnv() as EnvFields;
  }

  static String? get oneSignalAppId => _instance.oneSignalAppId;

  static String? get openAIAPIKey => (constOpenaiApiKey.isNotEmpty)
      ? constOpenaiApiKey
      : _instance.openAIAPIKey;

  static String? get instabugApiKey => _instance.instabugApiKey;

  static String? get mixpanelProjectToken =>
      (constMixpanelProjectToken.isNotEmpty)
          ? constMixpanelProjectToken
          : _instance.mixpanelProjectToken;

  static String? get apiBaseUrl =>
      (constApiBaseUrl.isNotEmpty) ? constApiBaseUrl : _instance.apiBaseUrl;

  static String? get growthbookApiKey => (constGrowthBookApiKey.isNotEmpty)
      ? constGrowthBookApiKey
      : _instance.growthbookApiKey;

  static String? get googleMapsApiKey => (constGoogleMapsApiKey.isNotEmpty)
      ? constGoogleMapsApiKey
      : _instance.googleMapsApiKey;

  static String? get rechargeAppApiKey =>
      (constRechargeAppApiKey.isNotEmpty) ? constRechargeAppApiKey : _instance.rechargeAppApiKey;
}

abstract class EnvFields {
  String? get oneSignalAppId;

  String? get openAIAPIKey;

  String? get instabugApiKey;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;

  String? get rechargeAppApiKey;
}
