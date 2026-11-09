import 'package:omi/env/env.dart';

/// Home fixtures have no service credentials and can only name loopback.
class HomeFixtureEnv implements EnvFields {
  @override
  String get apiBaseUrl => 'http://127.0.0.1:1/';
  @override
  String? get posthogApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool get useWebAuth => false;
  @override
  bool get useAuthCustomToken => false;
}
