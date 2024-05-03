import 'package:envied/envied.dart';

part 'env.g.dart';

@Envied(path: '.env')
abstract class Env {
  // OpenAI
  @EnviedField(varName: 'OPENAI_API_KEY')
  static const String openAIApiKey = _Env.openAIApiKey;
  @EnviedField(varName: 'DEEPGRAM_API_KEY')
  static const String deepgramApiKey = _Env.openAIApiKey;
}
