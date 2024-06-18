import 'package:envied/envied.dart';
import 'package:friend_private/flavors.dart';

part 'env.g.dart';

class Env {
  static bool get isDev => Flavor.development == F.appFlavor;

  static String? get sentryDSNKey => isDev ? EnvDev.sentryDSNKey : EnvProd.sentryDSNKey;
  static String? get openAIAPIKey => isDev ? EnvDev.openAIAPIKey : EnvProd.openAIAPIKey;
  static String? get deepgramApiKey => isDev ? EnvDev.deepgramApiKey : EnvProd.deepgramApiKey;
  static String? get instabugApiKey => isDev ? EnvDev.instabugApiKey : EnvProd.instabugApiKey;
  static String get pineconeApiKey => isDev ? EnvDev.pineconeApiKey : EnvProd.pineconeApiKey;
  static String get pineconeIndexUrl => isDev ? EnvDev.pineconeIndexUrl : EnvProd.pineconeIndexUrl;
  static String get pineconeIndexNamespace => isDev ? EnvDev.pineconeIndexNamespace : EnvProd.pineconeIndexNamespace;
  static String? get mixpanelProjectToken => isDev ? EnvDev.mixpanelProjectToken : EnvProd.mixpanelProjectToken;
  static String? get customTranscriptApiBaseUrl =>
      isDev ? EnvDev.customTranscriptApiBaseUrl : EnvProd.customTranscriptApiBaseUrl;
}

@Envied(path: '.env.dev', allowOptionalFields: true)
abstract class EnvDev {
  @EnviedField(varName: 'SENTRY_DSN_KEY', obfuscate: true)
  static String? sentryDSNKey = _EnvDev.sentryDSNKey;

  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  static String? openAIAPIKey = _EnvDev.openAIAPIKey;

  @EnviedField(varName: 'DEEPGRAM_API_KEY', obfuscate: true)
  static String? deepgramApiKey = _EnvDev.deepgramApiKey;

  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  static String? instabugApiKey = _EnvDev.instabugApiKey;

  // Pinecone
  @EnviedField(varName: 'PINECONE_API_KEY', obfuscate: true)
  static String pineconeApiKey = _EnvDev.pineconeApiKey;

  @EnviedField(varName: 'PINECONE_INDEX_URL', obfuscate: true)
  static String pineconeIndexUrl = _EnvDev.pineconeIndexUrl;

  @EnviedField(varName: 'PINECONE_INDEX_NAMESPACE', obfuscate: true)
  static String pineconeIndexNamespace = _EnvDev.pineconeIndexNamespace;

  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  static String? mixpanelProjectToken = _EnvDev.mixpanelProjectToken;

  @EnviedField(varName: 'CUSTOM_TRANSCRIPT_API_BASE_URL', obfuscate: true)
  static String? customTranscriptApiBaseUrl = _EnvDev.customTranscriptApiBaseUrl;
}

@Envied(path: '.env.prod', allowOptionalFields: true)
abstract class EnvProd {
  @EnviedField(varName: 'SENTRY_DSN_KEY', obfuscate: true)
  static String? sentryDSNKey = _EnvProd.sentryDSNKey;

  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  static String? openAIAPIKey = _EnvProd.openAIAPIKey;

  @EnviedField(varName: 'DEEPGRAM_API_KEY', obfuscate: true)
  static String? deepgramApiKey = _EnvProd.deepgramApiKey;

  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  static String? instabugApiKey = _EnvProd.instabugApiKey;

  // Pinecone
  @EnviedField(varName: 'PINECONE_API_KEY', obfuscate: true)
  static String pineconeApiKey = _EnvProd.pineconeApiKey;

  @EnviedField(varName: 'PINECONE_INDEX_URL', obfuscate: true)
  static String pineconeIndexUrl = _EnvProd.pineconeIndexUrl;

  @EnviedField(varName: 'PINECONE_INDEX_NAMESPACE', obfuscate: true)
  static String pineconeIndexNamespace = _EnvProd.pineconeIndexNamespace;

  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  static String? mixpanelProjectToken = _EnvProd.mixpanelProjectToken;

  @EnviedField(varName: 'CUSTOM_TRANSCRIPT_API_BASE_URL', obfuscate: true)
  static String? customTranscriptApiBaseUrl = _EnvProd.customTranscriptApiBaseUrl;
}
