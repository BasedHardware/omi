import 'package:friend_private/env/prod_env.dart';

import '../flavors.dart';
import 'dev_env.dart';

abstract class Env {
  static late final EnvFields _instance;

  static void init() {
    _instance = F.appFlavor == Flavor.dev ? DevEnv() : ProdEnv();
  }

  static String? get sentryDSNKey => _instance.sentryDSNKey;
  static String? get openAIAPIKey => _instance.openAIAPIKey;
  static String? get deepgramApiKey => _instance.deepgramApiKey;
  static String? get instabugApiKey => _instance.instabugApiKey;
  static String get pineconeApiKey => _instance.pineconeApiKey;
  static String get pineconeIndexUrl => _instance.pineconeIndexUrl;
  static String get pineconeIndexNamespace => _instance.pineconeIndexNamespace;
  static String? get mixpanelProjectToken => _instance.mixpanelProjectToken;
  static String? get customTranscriptApiBaseUrl =>
      _instance.customTranscriptApiBaseUrl;
}

abstract class EnvFields {
  String? get sentryDSNKey;
  String? get openAIAPIKey;
  String? get deepgramApiKey;
  String? get instabugApiKey;
  String get pineconeApiKey;
  String get pineconeIndexUrl;
  String get pineconeIndexNamespace;
  String? get mixpanelProjectToken;
  String? get customTranscriptApiBaseUrl;
}
