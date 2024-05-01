import 'package:envied/envied.dart';

part 'env.g.dart';

@Envied(path: '.env')
abstract class Env {
  // OpenAI
  @EnviedField(varName: 'OPENAI_API_KEY')
  static const String openAIApiKey = _Env.openAIApiKey;
  @EnviedField(varName: 'OPENAI_ORGANIZATION')
  static const String openAIOrganization = _Env.openAIOrganization;

  @EnviedField(varName: 'DEEPGRAM_API_KEY')
  static const String deepgramApiKey = _Env.openAIApiKey;

  @EnviedField(varName: 'PINECONE_API_KEY')
  static const String pineconeApiKey = _Env.pineconeApiKey;
  @EnviedField(varName: 'PINECONE_INDEX_URL')
  static const String pineconeIndexUrl = _Env.pineconeIndexUrl;
  @EnviedField(varName: 'PINECONE_INDEX_NAMESPACE')
  static const String pineconeIndexNamespace = _Env.pineconeIndexNamespace;
}
