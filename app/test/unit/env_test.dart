import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/flavors.dart';
import 'package:omi/startup_routing.dart';
import 'dart:io';

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
  String? get stagingApiUrl => null;
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
      validateApplicationStartupRouting(environment: Environment.prod, configuredApiBaseUrl: 'https://api.omi.me/');
      expect(Env.productionAgentProxyWsUrl, 'wss://agent.omi.me/v1/agent/ws');
    });

    test('Android production startup accepts the production API and WebSocket', () {
      validateApplicationStartupRouting(environment: Environment.prod, configuredApiBaseUrl: 'https://api.omi.me/');
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
          () => validateApplicationStartupRouting(environment: Environment.prod, configuredApiBaseUrl: endpoint),
          throwsStateError,
          reason: endpoint,
        );
      }
    });

    test('development startup remains configurable', () {
      expect(
        () => validateApplicationStartupRouting(
            environment: Environment.dev, configuredApiBaseUrl: 'https://api.omi.dev/'),
        returnsNormally,
      );
    });
  });

  test('main invokes the production startup routing seam before services initialize', () {
    // Static wiring tripwire: the behavioral cases above call the exact seam.
    final mainSource = File('lib/main.dart').readAsStringSync();
    expect(mainSource, contains('validateApplicationStartupRouting();'));
    expect(mainSource.indexOf('validateApplicationStartupRouting();'),
        lessThan(mainSource.indexOf('ServiceManager.init()')));
  });

  group('staging routing stays TestFlight-only', () {
    test('isUsingStagingApi is false when staging is not configured', () {
      // Android/production builds bake no STAGING_API_URL, so nothing can match.
      expect(Env.isStagingConfigured, isFalse);
      expect(Env.isUsingStagingApi, isFalse);
    });

    test('the staging override is reachable only inside the TestFlight branch', () {
      // Regression guard: a compile-time/build-identity flag once routed Android
      // beta to staging. The override must stay nested under isTestFlight.
      final mainSource = File('lib/main.dart').readAsStringSync();
      final testFlightBranch = mainSource.indexOf('if (isTestFlight) {');
      final override = mainSource.indexOf('Env.overrideApiBaseUrl(staging)');
      expect(testFlightBranch, greaterThan(-1));
      expect(override, greaterThan(testFlightBranch));
      // It must also be gated on the user's opt-in preference.
      final optIn = mainSource.indexOf('testFlightUseStagingApi');
      expect(optIn, greaterThan(testFlightBranch));
      expect(optIn, lessThan(override));
    });

    test('no build-identity flag can opt a non-TestFlight build into staging', () {
      final mainSource = File('lib/main.dart').readAsStringSync();
      final detectorSource = File('lib/utils/environment_detector.dart').readAsStringSync();
      for (final source in [mainSource, detectorSource]) {
        expect(source, isNot(contains('OMI_BETA_RELEASE_RING')));
        expect(source, isNot(contains('shouldUseBetaReleaseRing')));
      }
      // TestFlight detection itself must remain iOS-only.
      expect(detectorSource, contains('if (!Platform.isIOS) return false;'));
    });
  });
}
