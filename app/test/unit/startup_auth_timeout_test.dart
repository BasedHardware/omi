import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/startup_auth.dart';

void main() {
  group('resolveStartupAuth', () {
    test('a refresh that never returns does not block startup', () async {
      // The regression this guards. On iPhone 17 Pro / iOS 27.0 against a
      // Firebase Auth emulator on a non-loopback host, FirebaseAuth's forced
      // token refresh never returned — not an error, just silence. Because this
      // await sits before runApp(), the app showed the launch storyboard forever
      // and could not be started again until it was deleted, since the cached
      // session made every launch hang here.
      final neverCompletes = Completer<String?>();

      final result = await resolveStartupAuth(
        () => neverCompletes.future,
        timeout: const Duration(milliseconds: 50),
      );

      expect(result, isFalse, reason: 'a stalled refresh must resolve as unauthenticated, not hang');
    });

    test('a successful refresh is authenticated', () async {
      final result = await resolveStartupAuth(
        () async => 'a-real-token',
        timeout: const Duration(seconds: 5),
      );
      expect(result, isTrue);
    });

    test('a failed refresh is unauthenticated, exactly as before', () async {
      // getIdToken() already returns null on every failure branch and startup
      // already continued to the sign-in screen. The timeout must not change
      // that path.
      final result = await resolveStartupAuth(
        () async => null,
        timeout: const Duration(seconds: 5),
      );
      expect(result, isFalse);
    });

    test('a slow but successful refresh still authenticates', () async {
      // The timeout must not log out a user on a merely slow network.
      final result = await resolveStartupAuth(
        () => Future<String?>.delayed(const Duration(milliseconds: 20), () => 'token'),
        timeout: const Duration(seconds: 5),
      );
      expect(result, isTrue);
    });
  });
}
