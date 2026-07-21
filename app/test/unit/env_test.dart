import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';

/// Minimal EnvFields stub for testing Env logic in isolation.
/// Since Env._instance is late final (can only be set once per process),
/// we test with a single init and exercise the override/flag mechanisms.
class _TestEnvFields implements EnvFields {
  @override
  String? get openAIAPIKey => null;
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => 'https://api.omi.me/';
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
      Env.clearApiBaseUrlOverrideForTesting();
    });

    test('TestFlight production startup accepts the production API and WebSocket', () {
      Env.validateStartupRouting(productionFamily: true, configuredApiBaseUrl: 'https://api.omi.me/');
      expect(Env.productionAgentProxyWsUrl, 'wss://agent.omi.me/v1/agent/ws');
    });

    test('Android production startup accepts the production API and WebSocket', () {
      Env.validateStartupRouting(productionFamily: true, configuredApiBaseUrl: 'https://api.omi.me/');
      expect(Env.productionAgentProxyWsUrl, 'wss://agent.omi.me/v1/agent/ws');
    });

    test('production startup rejects legacy Beta, dev, staging, and arbitrary endpoints', () {
      for (final endpoint in [
        'https://api-beta.omi.me/',
        'https://api.omi.dev/',
        'https://staging.example.test/',
        'https://arbitrary.example.test/',
      ]) {
        expect(
          () => Env.validateStartupRouting(productionFamily: true, configuredApiBaseUrl: endpoint),
          throwsStateError,
          reason: endpoint,
        );
      }
    });

    test('development startup remains configurable', () {
      expect(
        () => Env.validateStartupRouting(productionFamily: false, configuredApiBaseUrl: 'https://api.omi.dev/'),
        returnsNormally,
      );
    });
  });
}
