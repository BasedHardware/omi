import 'package:envied/envied.dart';

import 'env.dart';

part 'dev_env.g.dart';

@Envied(allowOptionalFields: true, path: '.dev.env')
final class DevEnv implements EnvFields {
  DevEnv();

  @override
  @EnviedField(varName: 'SENTRY_DSN_KEY', obfuscate: true)
  final String? sentryDSNKey = _DevEnv.sentryDSNKey;

  @override
  @EnviedField(varName: 'OPENAI_API_KEY', obfuscate: true)
  final String? openAIAPIKey = _DevEnv.openAIAPIKey;

  @override
  @EnviedField(varName: 'DEEPGRAM_API_KEY', obfuscate: true)
  final String? deepgramApiKey = _DevEnv.deepgramApiKey;

  @override
  @EnviedField(varName: 'INSTABUG_API_KEY', obfuscate: true)
  final String? instabugApiKey = _DevEnv.instabugApiKey;

  @override
  @EnviedField(varName: 'PINECONE_API_KEY', obfuscate: true, defaultValue: '')
  final String pineconeApiKey = _DevEnv.pineconeApiKey;

  @override
  @EnviedField(varName: 'PINECONE_INDEX_URL', obfuscate: true, defaultValue: '')
  final String pineconeIndexUrl = _DevEnv.pineconeIndexUrl;

  @override
  @EnviedField(
      varName: 'PINECONE_INDEX_NAMESPACE', obfuscate: true, defaultValue: '')
  final String pineconeIndexNamespace = _DevEnv.pineconeIndexNamespace;

  @override
  @EnviedField(varName: 'MIXPANEL_PROJECT_TOKEN', obfuscate: true)
  final String? mixpanelProjectToken = _DevEnv.mixpanelProjectToken;

  @override
  @EnviedField(varName: 'CUSTOM_TRANSCRIPT_API_BASE_URL', obfuscate: true)
  final String? customTranscriptApiBaseUrl = _DevEnv.customTranscriptApiBaseUrl;
}
