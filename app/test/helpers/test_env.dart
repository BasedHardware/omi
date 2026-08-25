import 'package:omi/env/env.dart';

/// A minimal [EnvFields] so code paths that consult `Env` do not hit a
/// `LateInitializationError` in tests that never cared about configuration.
///
/// Eight test files already carry a private copy of this stub. This one exists so the files added
/// with the on-prem work do not make it nine: the auth service now asks `Env.useOidc` before choosing
/// a sign-in path (ADR-0034), which means tests written when that path touched no configuration at
/// all now need `Env` installed.
class TestEnvFields implements EnvFields {
  const TestEnvFields();

  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:8000/';
  @override
  String? get googleMapsApiKey => null;
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
  bool? get useWebAuth => false;
  @override
  bool? get useAuthCustomToken => false;
  @override
  String? get authBackend => 'firebase';
  @override
  String? get oidcIssuer => null;
  @override
  String? get oidcClientId => null;
  @override
  String? get oidcRedirectScheme => null;
  @override
  String? get notificationsBackend => 'fcm';
}

/// Installs [TestEnvFields] once per isolate. Safe to call from every `setUp`.
///
/// `Env._instance` is `late final`, so a second assignment throws — and a test file cannot know
/// whether another file in the same isolate already installed one. Swallowing that specific failure
/// is the whole point: the postcondition callers want is "Env is usable", not "Env was set by me".
void ensureTestEnv() {
  try {
    Env.init(const TestEnvFields());
  } catch (_) {
    // Already installed in this isolate.
  }
}
