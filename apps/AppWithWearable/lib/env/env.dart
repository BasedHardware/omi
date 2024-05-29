import 'package:envied/envied.dart';

part 'env.g.dart';

@Envied(allowOptionalFields: true)
abstract class Env {
  @EnviedField(varName: 'SENTRY_DSN_KEY', obfuscate: true)
  static String? sentryDSNKey = _Env.sentryDSNKey;

  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  static String? openAIAPIKey = _Env.openAIAPIKey;

  @EnviedField(varName: 'DEEPGRAM_API_KEY', obfuscate: true)
  static String? deepgramApiKey = _Env.deepgramApiKey;

  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  static String? instabugApiKey = _Env.instabugApiKey;

  // Pinecone
  @EnviedField(varName: 'PINECONE_API_KEY', obfuscate: true)
  static String pineconeApiKey = _Env.pineconeApiKey;

  @EnviedField(varName: 'PINECONE_INDEX_URL', obfuscate: true)
  static String pineconeIndexUrl = _Env.pineconeIndexUrl;

  @EnviedField(varName: 'PINECONE_INDEX_NAMESPACE', obfuscate: true)
  static String pineconeIndexNamespace = _Env.pineconeIndexNamespace;

  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  static String? mixpanelProjectToken = _Env.mixpanelProjectToken;

  @EnviedField(varName: 'CUSTOM_TRANSCRIPT_API_BASE_URL', obfuscate: true)
  static String? customTranscriptApiBaseUrl = _Env.customTranscriptApiBaseUrl;
}
