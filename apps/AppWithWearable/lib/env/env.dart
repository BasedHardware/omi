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
}
