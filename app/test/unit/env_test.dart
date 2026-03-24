import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';

/// Minimal EnvFields stub for testing Env logic in isolation.
/// Since Env._instance is late final (can only be set once per process),
/// we test with a single init and exercise the override/flag mechanisms.
class _TestEnvFields implements EnvFields {
  @override
  String? get stagingApiUrl => null; // triggers fallback

  @override
  String? get openAIAPIKey => null;
  @override
  String? get mixpanelProjectToken => null;
  @override
  String? get apiBaseUrl => 'https://api.prod.example.com/';
  @override
  String? get growthbookApiKey => null;
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
}

void main() {
  // Init once for the entire test suite (late final constraint)
  setUpAll(() {
    Env.init(_TestEnvFields());
  });

  group('Env.stagingApiUrl', () {
    test('falls back to default when stagingApiUrl is null/empty', () {
      // _TestEnvFields returns null for stagingApiUrl
      expect(Env.stagingApiUrl, 'https://api.omiapi.com/');
    });
  });

  group('Env.isUsingStagingApi', () {
    // Note: _TestEnvFields.stagingApiUrl returns null, which means
    // STAGING_API_URL is not explicitly configured. The implementation
    // requires explicit configuration to return true.
    test('false when override points to non-staging URL', () {
      Env.overrideApiBaseUrl('https://api.prod.example.com/');
      expect(Env.isUsingStagingApi, isFalse);
    });

    test('false when stagingApiUrl is not explicitly configured (null)', () {
      // Even though the override matches the fallback staging URL,
      // isUsingStagingApi requires _instance.stagingApiUrl to be non-null.
      Env.overrideApiBaseUrl('https://api.omiapi.com/');
      expect(Env.isUsingStagingApi, isFalse);
    });

    test('false when override differs from fallback', () {
      Env.overrideApiBaseUrl('https://something-else.example.com/');
      expect(Env.isUsingStagingApi, isFalse);
    });
  });

  group('Env.isTestFlight', () {
    test('can be set to false', () {
      Env.isTestFlight = false;
      expect(Env.isTestFlight, isFalse);
    });

    test('can be set to true', () {
      Env.isTestFlight = true;
      expect(Env.isTestFlight, isTrue);
      // Clean up
      Env.isTestFlight = false;
    });
  });

  group('Env.apiBaseUrl', () {
    test('returns override when set', () {
      Env.overrideApiBaseUrl('https://override.example.com/');
      expect(Env.apiBaseUrl, 'https://override.example.com/');
    });
  });
}
