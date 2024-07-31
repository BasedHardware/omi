import 'package:friend_private/env/dev_env.dart';

abstract class Env {
  static late final EnvFields _instance;

  static void init([EnvFields? instance]) {
    _instance = instance ?? DevEnv() as EnvFields;
  }

  static String? get oneSignalAppId => _instance.oneSignalAppId;

  static String? get sentryDSNKey => _instance.sentryDSNKey;

  static String? get openAIAPIKey => _instance.openAIAPIKey;

  static String? get deepgramApiKey => _instance.deepgramApiKey;

  static String? get instabugApiKey => _instance.instabugApiKey;

  static String get pineconeApiKey => _instance.pineconeApiKey;

  static String get pineconeIndexUrl => _instance.pineconeIndexUrl;

  static String get pineconeIndexNamespace => _instance.pineconeIndexNamespace;

  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;

  static String? get apiBaseUrl => _instance.apiBaseUrl;

  static String? get growthbookApiKey => _instance.growthbookApiKey;

  static String? get googleMapsApiKey => _instance.googleMapsApiKey;
}

abstract class EnvFields {
  String? get oneSignalAppId;

  String? get sentryDSNKey;

  String? get openAIAPIKey;

  String? get deepgramApiKey;

  String? get instabugApiKey;

  String get pineconeApiKey;

  String get pineconeIndexUrl;

  String get pineconeIndexNamespace;

  String? get mixpanelProjectToken;

  String? get apiBaseUrl;

  String? get growthbookApiKey;

  String? get googleMapsApiKey;
}
