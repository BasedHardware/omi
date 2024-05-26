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
  @EnviedField(varName: 'PINECONE_API_KEY')
  static const String pineconeApiKey = _Env.pineconeApiKey;

  @EnviedField(varName: 'PINECONE_INDEX_URL')
  static const String pineconeIndexUrl = _Env.pineconeIndexUrl;

  @EnviedField(varName: 'PINECONE_INDEX_NAMESPACE')
  static const String pineconeIndexNamespace = _Env.pineconeIndexNamespace;
}
