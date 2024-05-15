import 'package:envied/envied.dart';

part 'env.g.dart';

@Envied(allowOptionalFields: true)
abstract class Env {
  @EnviedField(varName: 'SENTRY_DSN_KEY', obfuscate: true)
  static String? sentryDSNKey = _Env.sentryDSNKey;
}
