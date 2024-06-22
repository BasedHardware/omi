import 'package:envied/envied.dart';

import 'env.dart';

part 'prod_env.g.dart';

@Envied(allowOptionalFields: true, path: '.env')
final class ProdEnv implements EnvFields {
  ProdEnv();

  @override
  @EnviedField(varName: 'SENTRY_DSN_KEY', obfuscate: true)
  final String? sentryDSNKey = _ProdEnv.sentryDSNKey;

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _ProdEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'DEEPGRAM_API_KEY', obfuscate: true)
  final String? deepgramApiKey = _ProdEnv.deepgramApiKey;

  @override
  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  final String? instabugApiKey = _ProdEnv.instabugApiKey;

  @override
  @EnviedField(varName: 'PINECONE_API_KEY', obfuscate: true, defaultValue: '')
  final String pineconeApiKey = _ProdEnv.pineconeApiKey;

  @override
  @EnviedField(varName: 'PINECONE_INDEX_URL', obfuscate: true, defaultValue: '')
  final String pineconeIndexUrl = _ProdEnv.pineconeIndexUrl;

  @override
  @EnviedField(
      varName: 'PINECONE_INDEX_NAMESPACE', obfuscate: true, defaultValue: '')
  final String pineconeIndexNamespace = _ProdEnv.pineconeIndexNamespace;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _ProdEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'CUSTOM_TRANSCRIPT_API_BASE_URL', obfuscate: true)
  final String? customTranscriptApiBaseUrl =
      _ProdEnv.customTranscriptApiBaseUrl;
}
