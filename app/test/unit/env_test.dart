import 'package:flutter_test/flutter_test.dart';
import 'package:omi/env/env.dart';
import 'package:omi/env/environment_profile.dart';
import 'package:omi/flavors.dart';
import 'package:omi/startup_routing.dart';
import 'dart:io';

/// Minimal EnvFields stub for testing Env logic in isolation.
/// Since Env._instance is late final (can only be set once per process),
/// we test with a single init and exercise the override/flag mechanisms.
class _TestEnvFields implements EnvFields {
  @override
  String? get posthogApiKey => null;
  @override
  String? get apiBaseUrl => null;
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

  group('mobile environment profiles', () {
    test('local development is emulator-first and does not allow production data', () {
      expect(AppEnvironmentProfile.localDev.defaultApiBaseUrl, 'http://127.0.0.1:8000/');
      expect(AppEnvironmentProfile.localDev.firebaseProjectId, 'demo-omi-local');
      expect(AppEnvironmentProfile.localDev.usesFirebaseAuthEmulator, isTrue);
      expect(AppEnvironmentProfile.localDev.allowsProductionData, isFalse);
    });

    test('mobile beta explicitly pairs production Firebase with the dev serving plane', () {
      expect(AppEnvironmentProfile.mobileBeta.defaultApiBaseUrl, 'https://api.omiapi.com/');
      expect(AppEnvironmentProfile.mobileBeta.firebaseProjectId, 'based-hardware');
      expect(AppEnvironmentProfile.mobileBeta.usesFirebaseAuthEmulator, isFalse);
      expect(AppEnvironmentProfile.mobileBeta.allowsProductionData, isTrue);
      expect(AppEnvironmentProfile.mobileBeta.authCallbackScheme, 'omi-beta');
    });

    test('mobile beta keeps OAuth on the production identity plane', () {
      expect(
        Env.authApiBaseUrlForProfile(AppEnvironmentProfile.mobileBeta, servingApiBaseUrl: 'https://api.omiapi.com/'),
        Env.productionApiBaseUrl,
      );
    });

    test('local prod pairs production Firebase with a developer-chosen backend', () {
      expect(AppEnvironmentProfile.localProd.firebaseProjectId, 'based-hardware');
      expect(AppEnvironmentProfile.localProd.usesFirebaseAuthEmulator, isFalse);
      expect(AppEnvironmentProfile.localProd.allowsProductionData, isTrue);
      expect(AppEnvironmentProfile.localProd.authCallbackScheme, 'omi');
    });

    test('local profile rejects a production Firebase project', () {
      expect(
        () =>
            Env.validateFirebaseProject(projectId: 'based-hardware', configuredProfile: AppEnvironmentProfile.localDev),
        throwsStateError,
      );
    });

    test('flavor defaults map to production and local profiles', () {
      expect(AppEnvironmentProfile.forFlavor(productionFlavor: true), AppEnvironmentProfile.production);
      expect(AppEnvironmentProfile.forFlavor(productionFlavor: false), AppEnvironmentProfile.localDev);
    });

    test('production iOS config keeps the production Google redirect client id', () {
      final prodConfig = File('ios/Flutter/prodRelease.xcconfig').readAsStringSync();

      expect(
        prodConfig,
        contains('GOOGLE_REVERSE_CLIENT_ID=com.googleusercontent.apps.208440318997-ukinsq3sijhcetkhr26ssqp1terbq7as'),
      );
      expect(prodConfig, isNot(contains('GOOGLE_REVERSE_CLIENT_ID=com.googleusercontent.apps.1031333818730-')));
    });
  });

  group('Env.apiBaseUrl', () {
    test('uses the local emulator API when development env has no URL', () {
      expect(Env.apiBaseUrl, 'http://127.0.0.1:8000/');
    });

    test('returns override when set', () {
      Env.overrideApiBaseUrl('https://override.example.com/');
      expect(Env.apiBaseUrl, 'https://override.example.com/');
      Env.clearApiBaseUrlOverrideForTesting();
    });

    test('TestFlight production startup accepts the production API', () {
      validateApplicationStartupRouting(environment: Environment.prod, configuredApiBaseUrl: 'https://api.omi.me/');
    });

    test('Android production startup accepts the production API', () {
      validateApplicationStartupRouting(environment: Environment.prod, configuredApiBaseUrl: 'https://api.omi.me/');
    });

    test('mobile beta accepts the dev serving plane with production identity', () {
      Env.validateStartupRouting(
        productionFamily: true,
        configuredProfile: AppEnvironmentProfile.mobileBeta,
        configuredApiBaseUrl: 'https://api.omiapi.com/',
      );
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

    test('local dev accepts loopback and every private-network range, including CGNAT', () {
      for (final endpoint in [
        'http://127.0.0.1:8000/',
        'http://localhost:8000/',
        'http://10.0.0.5:8000/',
        'http://172.16.0.5:8000/',
        'http://172.31.255.254:8000/',
        'http://192.168.1.20:8000/',
        // 100.64.0.0/10 (RFC 6598, carrier-grade NAT) is the range Tailscale
        // assigns. A physical device cannot reach the local harness any other
        // way — the harness binds loopback only by design — so rejecting this
        // range stranded the app on a blank splash with no diagnostic.
        'http://100.64.0.1:8000/',
        'http://100.105.2.5:8000/',
        'http://100.127.255.254:8000/',
      ]) {
        Env.validateStartupRouting(
          productionFamily: false,
          configuredProfile: AppEnvironmentProfile.localDev,
          configuredApiBaseUrl: endpoint,
        );
      }
    });

    test('local dev still rejects public endpoints and the edges just outside CGNAT', () {
      for (final endpoint in [
        'https://api.omi.me/',
        'https://api.omiapi.com/',
        // 100.63.x and 100.128.x sit immediately outside 100.64.0.0/10 and must
        // stay rejected — widening this must not degrade into "any 100.x host".
        'http://100.63.255.255:8000/',
        'http://100.128.0.1:8000/',
        'http://8.8.8.8:8000/',
      ]) {
        expect(
          () => Env.validateStartupRouting(
            productionFamily: false,
            configuredProfile: AppEnvironmentProfile.localDev,
            configuredApiBaseUrl: endpoint,
          ),
          throwsStateError,
          reason: endpoint,
        );
      }
    });

    test('local prod accepts loopback, private-network, and tunnel endpoints in debug builds', () {
      for (final endpoint in [
        'http://127.0.0.1:8000/',
        'http://192.168.1.20:8000/',
        'https://example.ngrok-free.app/',
      ]) {
        Env.validateStartupRouting(
          productionFamily: true,
          configuredProfile: AppEnvironmentProfile.localProd,
          configuredApiBaseUrl: endpoint,
          releaseBuild: false,
        );
      }
    });

    test('local prod is rejected in release builds', () {
      expect(
        () => Env.validateStartupRouting(
          productionFamily: true,
          configuredProfile: AppEnvironmentProfile.localProd,
          configuredApiBaseUrl: 'http://127.0.0.1:8000/',
          releaseBuild: true,
        ),
        throwsStateError,
      );
    });

    test('local prod rejects a malformed endpoint', () {
      expect(
        () => Env.validateStartupRouting(
          productionFamily: true,
          configuredProfile: AppEnvironmentProfile.localProd,
          configuredApiBaseUrl: 'not a url',
          releaseBuild: false,
        ),
        throwsStateError,
      );
    });

    test('local development startup accepts the emulator API', () {
      expect(
        () => validateApplicationStartupRouting(
          environment: Environment.dev,
          configuredApiBaseUrl: 'http://127.0.0.1:8000/',
        ),
        returnsNormally,
      );
    });

    test('local development rejects the remote dev serving plane', () {
      expect(
        () => validateApplicationStartupRouting(
          environment: Environment.dev,
          configuredApiBaseUrl: 'https://api.omiapi.com/',
        ),
        throwsStateError,
      );
    });
  });

  test('main invokes the production startup routing seam before services initialize', () {
    // Static wiring tripwire: the behavioral cases above call the exact seam.
    final mainSource = File('lib/main.dart').readAsStringSync();
    expect(mainSource, contains('validateApplicationStartupRouting();'));
    expect(
      mainSource.indexOf('validateApplicationStartupRouting();'),
      lessThan(mainSource.indexOf('ServiceManager.init()')),
    );
    // Same guarantee as before — the project id of the Firebase app main.dart ends
    // up with is fed to Env.validateFirebaseProject — but the statement it used to
    // name verbatim now lives in ensureFirebaseApp() (lib/startup_firebase.dart),
    // which applies it to the freshly initialized app, the already-running native
    // app, and the app adopted after [core/duplicate-app] alike. So this pins the
    // wiring instead of one branch's text; that ensureFirebaseApp actually calls it
    // on every one of those paths is asserted behaviorally in
    // test/unit/startup_firebase_duplicate_app_test.dart.
    expect(
      mainSource,
      matches(
        RegExp(
          r'projectIdOf:\s*\(app\)\s*=>\s*app\.options\.projectId,\s*'
          r'validateProject:\s*\(projectId\)\s*=>\s*Env\.validateFirebaseProject\(projectId:\s*projectId\),',
        ),
      ),
    );
  });
}
