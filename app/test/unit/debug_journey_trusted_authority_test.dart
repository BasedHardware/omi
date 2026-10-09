import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:omi/backend/http/http_pool_manager.dart';
import 'package:omi/backend/http/shared.dart';
import 'package:omi/env/env.dart';
import 'package:omi/services/dev_controls/journey_faults.dart';
import 'package:omi/utils/platform/platform_manager.dart';

void main() {
  setUpAll(PlatformManager.initializeForLocalHarness);

  tearDown(() {
    Env.debugJourneyTrustPermitted = kDebugMode;
    Env.clearApiBaseUrlOverrideForTesting();
    JourneyFaultGate.instance.clearAll();
  });

  group('debug journey fixture trust', () {
    test('a registered loopback fixture is trusted only after the journey boot arms it', () {
      const fixture = 'http://127.0.0.1:9/v1/conversations/seeded';

      expect(shouldAttachOmiCredentials(fixture), isFalse, reason: 'unregistered fixture stays untrusted');

      Env.armDebugJourneyCredentialTrust();
      expect(shouldAttachOmiCredentials(fixture), isFalse, reason: 'arming alone does not trust every loopback host');

      Env.addDebugTrustedAuthority('127.0.0.1');
      expect(shouldAttachOmiCredentials(fixture), isTrue);
      expect(shouldAttachOmiCredentials('http://localhost:9/v1/conversations/seeded'), isFalse,
          reason: 'trust is exact host membership, not every loopback name');
      expect(
        shouldHonorRequestedOmiAuth(requested: true, customBackendActive: true, url: fixture),
        isTrue,
        reason: 'the harness bearer must be requested once the fixture is trusted',
      );
      expect(shouldAttachOmiCredentials('https://api.omi.me/v1/users/me'), isTrue);
      expect(shouldAttachOmiCredentials('https://self-hosted.example.test/v1/users/me'), isFalse);
    });

    test('release and profile cannot arm or register a trusted authority', () {
      Env.debugJourneyTrustPermitted = false;

      expect(() => Env.armDebugJourneyCredentialTrust(), throwsA(isA<AssertionError>()));
      expect(() => Env.addDebugTrustedAuthority('127.0.0.1'), throwsA(isA<AssertionError>()));
      expect(shouldAttachOmiCredentials('http://127.0.0.1:9/v1/conversations/seeded'), isFalse);
      expect(shouldAttachOmiCredentials('https://api.omi.me/v1/users/me'), isTrue,
          reason: 'refusing fixture trust must not drop official Omi hosts');
    });

    test('registration without the journey boot flag asserts and does not trust the host', () {
      expect(() => Env.addDebugTrustedAuthority('127.0.0.1'), throwsA(isA<AssertionError>()));
      expect(shouldAttachOmiCredentials('http://127.0.0.1:9/v1/conversations/seeded'), isFalse);
    });

    test('a non-loopback host cannot be registered even while the journey boot is armed', () {
      Env.armDebugJourneyCredentialTrust();

      expect(() => Env.addDebugTrustedAuthority('self-hosted.example.test'), throwsA(isA<AssertionError>()));
      expect(shouldAttachOmiCredentials('https://self-hosted.example.test/v1/users/me'), isFalse);
      expect(shouldAttachOmiCredentials('http://127.0.0.1:9/v1/conversations/seeded'), isFalse);
    });

    test('a user-configured loopback override stays credential-free until a journey registers it', () async {
      Env.overrideApiBaseUrl('http://127.0.0.1:9/');

      final blocked = await buildHeaders(
        requireAuthCheck: false,
        url: 'http://127.0.0.1:9/v1/conversations/seeded',
        method: 'GET',
        fromHeaders: const {'Authorization': 'Bearer leaked'},
      );
      expect(blocked.keys.map((key) => key.toLowerCase()), isNot(contains('authorization')));

      Env.armDebugJourneyCredentialTrust();
      Env.addDebugTrustedAuthority('127.0.0.1');
      final trusted = await buildHeaders(
        requireAuthCheck: false,
        url: 'http://127.0.0.1:9/v1/conversations/seeded',
        method: 'GET',
        fromHeaders: const {'Authorization': 'Bearer synthetic-journey-bearer'},
      );
      expect(trusted['Authorization'], 'Bearer synthetic-journey-bearer');
    });

    test('an armed fixture does not let a user-configured custom backend receive credentials', () async {
      Env.armDebugJourneyCredentialTrust();
      Env.addDebugTrustedAuthority('127.0.0.1');
      Env.overrideApiBaseUrl('https://self-hosted.example.test/');

      final headers = await buildHeaders(
        requireAuthCheck: false,
        url: 'https://self-hosted.example.test/v1/users/me',
        method: 'POST',
        fromHeaders: const {
          'authorization': 'Bearer leaked',
          'X-Account-Generation': '42',
          'X-Request-Id': 'preserved',
        },
      );

      expect(headers.keys.map((key) => key.toLowerCase()), isNot(contains('authorization')));
      expect(headers.keys.map((key) => key.toLowerCase()), isNot(contains('x-account-generation')));
      expect(headers['X-Request-Id'], 'preserved');
      expect(
        shouldHonorRequestedOmiAuth(
          requested: true,
          customBackendActive: true,
          url: 'https://self-hosted.example.test/v1/users/me',
        ),
        isFalse,
      );
    });
  });

  group('wrong-owner fault chokepoint', () {
    test('swaps an existing Authorization header for the fixture wrong-owner bearer', () {
      JourneyFaultGate.instance.arm(JourneyFault.wrongOwnerSession);
      final request = http.Request('GET', Uri.parse('http://127.0.0.1:9/v1/conversations/seeded'));
      request.headers['Authorization'] = 'Bearer synthetic-journey-bearer';

      HttpPoolManager.instance.applyJourneyFaultsForTesting(request);

      expect(request.headers['Authorization'], 'Bearer synthetic-wrong-owner-session-token');
    });

    test('does not invent an Authorization header when the request has none', () {
      JourneyFaultGate.instance.arm(JourneyFault.wrongOwnerSession);
      final request = http.Request('GET', Uri.parse('http://127.0.0.1:9/v1/conversations/seeded'));

      HttpPoolManager.instance.applyJourneyFaultsForTesting(request);

      expect(request.headers.containsKey('Authorization'), isFalse);
    });
  });
}
