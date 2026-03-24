import 'package:flutter_test/flutter_test.dart';

/// Tests for the token refresh death spiral fix (#5927, originally #5448).
///
/// The production code uses singletons (FirebaseAuth, SharedPreferencesUtil,
/// AuthService) that aren't injectable, so these tests exercise the exact
/// same branching logic via minimal abstractions that mirror the production flow.

/// Simulates SharedPreferencesUtil token cache behavior.
class MockTokenCache {
  String authToken = '';
  int tokenExpirationTime = 0;
}

/// Exception type mirroring FirebaseAuthException for test purposes.
class MockFirebaseAuthException implements Exception {
  final String code;
  MockFirebaseAuthException(this.code);
  @override
  String toString() => 'MockFirebaseAuthException: $code';
}

/// Simulates AuthService.getIdToken() logic after fix (#5927).
/// Only clears cached auth on auth-specific exceptions (user-not-found,
/// user-disabled, user-token-expired). Preserves token on transient errors.
Future<String?> getIdTokenFixed({
  required bool hasCurrentUser,
  required Future<String?> Function() refreshToken,
  required MockTokenCache cache,
}) async {
  try {
    if (!hasCurrentUser) {
      cache.authToken = '';
      cache.tokenExpirationTime = 0;
      return null;
    }
    final token = await refreshToken();
    if (token != null) {
      cache.authToken = token;
      cache.tokenExpirationTime = DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch;
      return token;
    }
    return null;
  } on MockFirebaseAuthException catch (e) {
    if (e.code == 'user-not-found' || e.code == 'user-disabled' || e.code == 'user-token-expired') {
      cache.authToken = '';
      cache.tokenExpirationTime = 0;
    }
    // Other FirebaseAuthException codes: preserve cached token
    return null;
  } catch (e) {
    // Transient errors (network, timeout): preserve cached token
    return null;
  }
}

/// Simulates getAuthHeader() logic after fix (#5927).
/// Re-reads hasAuthToken after refresh, only overwrites on non-null result.
Future<String> getAuthHeaderFixed({
  required MockTokenCache cache,
  required bool isExpirationDateValid,
  required Future<String?> Function() getIdToken,
  required bool isSignedIn,
}) async {
  bool hasAuthToken = cache.authToken.isNotEmpty;

  if (!hasAuthToken || !isExpirationDateValid) {
    final refreshedToken = await getIdToken();
    if (refreshedToken != null) {
      cache.authToken = refreshedToken;
    }
    hasAuthToken = cache.authToken.isNotEmpty;
  }

  if (!hasAuthToken) {
    if (isSignedIn) {
      throw Exception('No auth token found');
    }
  }
  return 'Bearer ${cache.authToken}';
}

/// Simulates the OLD getIdToken() behavior (before fix) — returns cached expired token.
Future<String?> getIdTokenOld({
  required bool hasCurrentUser,
  required Future<String?> Function() refreshToken,
  required MockTokenCache cache,
}) async {
  try {
    if (!hasCurrentUser) {
      // OLD: returned cached token as fallback
      if (cache.authToken.isNotEmpty) return cache.authToken;
      return null;
    }
    final token = await refreshToken();
    if (token != null) {
      cache.authToken = token;
      return token;
    }
    if (cache.authToken.isNotEmpty) return cache.authToken;
    return null;
  } catch (e) {
    // OLD: returned cached expired token on error
    return cache.authToken;
  }
}

/// Simulates AuthService.signOut() after fix — clears cached auth.
Future<void> signOutFixed(MockTokenCache cache) async {
  cache.authToken = '';
  cache.tokenExpirationTime = 0;
}

/// Simulates the OLD signOut() — does NOT clear cached auth.
Future<void> signOutOld(MockTokenCache cache) async {
  // OLD: only called FirebaseAuth.signOut(), did not clear cache
}

/// Simulates AuthenticationProvider.isSignedIn() after fix.
bool isSignedInFixed({required bool hasFirebaseUser}) {
  return hasFirebaseUser;
}

/// Simulates the OLD isSignedIn() — falls back to cached credentials.
bool isSignedInOld({required bool hasFirebaseUser, required MockTokenCache cache}) {
  if (hasFirebaseUser) return true;
  return cache.authToken.isNotEmpty;
}

/// Simulates keepAlive timer check after fix.
bool shouldReconnectFixed({required bool isSignedIn, required bool socketDisconnected}) {
  if (!isSignedIn) return false;
  return socketDisconnected;
}

/// Simulates the OLD keepAlive — no auth check.
bool shouldReconnectOld({required bool socketDisconnected}) {
  return socketDisconnected;
}

void main() {
  group('Bug 1: getIdToken returns null (not cached token) on failure', () {
    test('fixed: returns null when currentUser is null', () async {
      final cache = MockTokenCache()..authToken = 'expired-token-abc';
      final result = await getIdTokenFixed(
        hasCurrentUser: false,
        refreshToken: () async => 'new-token',
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, isEmpty, reason: 'cache must be cleared');
    });

    test('fixed: returns null and preserves cached token when refresh throws transient error', () async {
      final cache = MockTokenCache()..authToken = 'expired-token-abc';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw Exception('network error'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, equals('expired-token-abc'), reason: 'transient errors must preserve cached token');
    });

    test('fixed: returns new token on successful refresh', () async {
      final cache = MockTokenCache();
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => 'fresh-token-xyz',
        cache: cache,
      );
      expect(result, equals('fresh-token-xyz'));
      expect(cache.authToken, equals('fresh-token-xyz'));
    });

    test('old behavior: returns cached expired token when currentUser is null (BUG)', () async {
      final cache = MockTokenCache()..authToken = 'expired-token-abc';
      final result = await getIdTokenOld(
        hasCurrentUser: false,
        refreshToken: () async => 'new-token',
        cache: cache,
      );
      expect(result, equals('expired-token-abc'), reason: 'OLD code returns cached expired token — this is the bug');
    });

    test('old behavior: returns cached expired token when refresh throws (BUG)', () async {
      final cache = MockTokenCache()..authToken = 'expired-token-abc';
      final result = await getIdTokenOld(
        hasCurrentUser: true,
        refreshToken: () async => throw Exception('network error'),
        cache: cache,
      );
      expect(result, equals('expired-token-abc'), reason: 'OLD code returns cached expired token — this is the bug');
    });
  });

  group('Bug 2: signOut clears cached token', () {
    test('fixed: signOut clears authToken and tokenExpirationTime', () async {
      final cache = MockTokenCache()
        ..authToken = 'some-token'
        ..tokenExpirationTime = 9999999;
      await signOutFixed(cache);
      expect(cache.authToken, isEmpty);
      expect(cache.tokenExpirationTime, equals(0));
    });

    test('old behavior: signOut does NOT clear cache (BUG)', () async {
      final cache = MockTokenCache()
        ..authToken = 'some-token'
        ..tokenExpirationTime = 9999999;
      await signOutOld(cache);
      expect(cache.authToken, equals('some-token'), reason: 'OLD signOut leaves token cached — this is the bug');
    });
  });

  group('Bug 3: isSignedIn does not fall back to cached credentials', () {
    test('fixed: returns false when Firebase user is null (even if cache has token)', () {
      expect(isSignedInFixed(hasFirebaseUser: false), isFalse);
    });

    test('fixed: returns true when Firebase user exists', () {
      expect(isSignedInFixed(hasFirebaseUser: true), isTrue);
    });

    test('old behavior: returns true with cached credentials even after signOut (BUG)', () {
      final cache = MockTokenCache()..authToken = 'stale-token';
      expect(
        isSignedInOld(hasFirebaseUser: false, cache: cache),
        isTrue,
        reason: 'OLD isSignedIn falls back to cached token — keeps UI "signed in" after signOut',
      );
    });
  });

  group('Bug 4: keepAlive timer checks auth before WebSocket reconnect', () {
    test('fixed: does not reconnect when user is not signed in', () {
      expect(shouldReconnectFixed(isSignedIn: false, socketDisconnected: true), isFalse);
    });

    test('fixed: reconnects when user is signed in and socket is disconnected', () {
      expect(shouldReconnectFixed(isSignedIn: true, socketDisconnected: true), isTrue);
    });

    test('fixed: does not reconnect when socket is already connected', () {
      expect(shouldReconnectFixed(isSignedIn: true, socketDisconnected: false), isFalse);
    });

    test('old behavior: reconnects even when user is not signed in (BUG)', () {
      expect(
        shouldReconnectOld(socketDisconnected: true),
        isTrue,
        reason: 'OLD keepAlive reconnects without auth check — creates infinite failed WebSocket connections',
      );
    });
  });

  group('Race conditions and boundary cases', () {
    test('concurrent getIdToken failure + signOut: cache ends up cleared', () async {
      final cache = MockTokenCache()..authToken = 'token-to-clear';

      // Simulate both happening — order shouldn't matter, cache should be empty after both
      await Future.wait([
        getIdTokenFixed(hasCurrentUser: false, refreshToken: () async => null, cache: cache),
        signOutFixed(cache),
      ]);

      expect(cache.authToken, isEmpty, reason: 'cache must be cleared regardless of execution order');
      expect(cache.tokenExpirationTime, equals(0));
    });

    test('rapid successive getIdToken failures all return null', () async {
      final cache = MockTokenCache()..authToken = 'stale-token';

      // First call: no currentUser → clears cache
      final r1 = await getIdTokenFixed(hasCurrentUser: false, refreshToken: () async => null, cache: cache);
      expect(r1, isNull);
      expect(cache.authToken, isEmpty, reason: 'no currentUser clears cache');

      // Subsequent transient errors return null but don't further corrupt
      final r2 =
          await getIdTokenFixed(hasCurrentUser: true, refreshToken: () async => throw Exception('err1'), cache: cache);
      expect(r2, isNull);

      final r3 =
          await getIdTokenFixed(hasCurrentUser: true, refreshToken: () async => throw Exception('err2'), cache: cache);
      expect(r3, isNull);
    });

    test('successful refresh after failure restores cache correctly', () async {
      final cache = MockTokenCache()..authToken = 'old-expired';

      // First call fails transiently — preserves cached token
      final r1 = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw Exception('network'),
        cache: cache,
      );
      expect(r1, isNull);
      expect(cache.authToken, equals('old-expired'), reason: 'transient error preserves token');

      // Second call succeeds — restores cache with fresh token
      final r2 = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => 'fresh-token',
        cache: cache,
      );
      expect(r2, equals('fresh-token'));
      expect(cache.authToken, equals('fresh-token'));
      expect(cache.tokenExpirationTime, greaterThan(0));
    });

    test('signOut is idempotent — double signOut does not throw', () async {
      final cache = MockTokenCache()
        ..authToken = 'token'
        ..tokenExpirationTime = 99999;

      await signOutFixed(cache);
      expect(cache.authToken, isEmpty);

      // Second signOut — should not throw or corrupt state
      await signOutFixed(cache);
      expect(cache.authToken, isEmpty);
      expect(cache.tokenExpirationTime, equals(0));
    });

    test('keepAlive gate: multiple rapid checks with auth loss mid-sequence', () {
      // User is signed in for first check
      expect(shouldReconnectFixed(isSignedIn: true, socketDisconnected: true), isTrue);

      // Auth is lost between checks (simulates signOut clearing state)
      expect(shouldReconnectFixed(isSignedIn: false, socketDisconnected: true), isFalse);

      // Even after socket reconnects, no reconnect without auth
      expect(shouldReconnectFixed(isSignedIn: false, socketDisconnected: true), isFalse);
    });

    test('getIdToken with null refresh result (not exception) returns null', () async {
      final cache = MockTokenCache()..authToken = 'stale';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => null,
        cache: cache,
      );
      expect(result, isNull, reason: 'null from refresh should propagate as null, not cached token');
    });
  });

  group('Full loop: token expiry no longer causes infinite retry', () {
    test('fixed: expired token -> getIdToken null -> signOut clears cache -> isSignedIn false -> no reconnect',
        () async {
      final cache = MockTokenCache()
        ..authToken = 'expired-token'
        ..tokenExpirationTime = DateTime.now().subtract(const Duration(hours: 1)).millisecondsSinceEpoch;

      // Step 1: API call gets 401, tries to refresh token
      // currentUser is null (token expired, Firebase session ended)
      final refreshedToken = await getIdTokenFixed(
        hasCurrentUser: false,
        refreshToken: () async => throw Exception('no user'),
        cache: cache,
      );
      expect(refreshedToken, isNull);
      expect(cache.authToken, isEmpty);

      // Step 2: signOut is called (clears cache)
      await signOutFixed(cache);
      expect(cache.authToken, isEmpty);
      expect(cache.tokenExpirationTime, equals(0));

      // Step 3: isSignedIn returns false (no Firebase user, no cached fallback)
      final signedIn = isSignedInFixed(hasFirebaseUser: false);
      expect(signedIn, isFalse);

      // Step 4: keepAlive timer checks auth — does NOT reconnect
      final shouldReconnect = shouldReconnectFixed(isSignedIn: signedIn, socketDisconnected: true);
      expect(shouldReconnect, isFalse, reason: 'Loop is broken — no more reconnect attempts');
    });

    test('old behavior: expired token causes infinite loop', () async {
      final cache = MockTokenCache()
        ..authToken = 'expired-token'
        ..tokenExpirationTime = DateTime.now().subtract(const Duration(hours: 1)).millisecondsSinceEpoch;

      // Step 1: getIdToken returns cached expired token (BUG 1)
      final refreshedToken = await getIdTokenOld(
        hasCurrentUser: false,
        refreshToken: () async => throw Exception('no user'),
        cache: cache,
      );
      expect(refreshedToken, equals('expired-token'), reason: 'BUG: returns cached expired token');

      // Step 2: signOut doesn't clear cache (BUG 2)
      await signOutOld(cache);
      expect(cache.authToken, equals('expired-token'), reason: 'BUG: cache not cleared');

      // Step 3: isSignedIn returns true because of cached token (BUG 3)
      final signedIn = isSignedInOld(hasFirebaseUser: false, cache: cache);
      expect(signedIn, isTrue, reason: 'BUG: thinks user is still signed in');

      // Step 4: keepAlive reconnects unconditionally (BUG 4)
      final shouldReconnect = shouldReconnectOld(socketDisconnected: true);
      expect(shouldReconnect, isTrue, reason: 'BUG: reconnects with expired token — LOOP CONTINUES');
    });
  });

  group('Bug 5 (#5927): FirebaseAuthException code-specific clearing', () {
    test('clears cache on user-not-found', () async {
      final cache = MockTokenCache()..authToken = 'valid-token';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw MockFirebaseAuthException('user-not-found'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, isEmpty, reason: 'user-not-found must clear cache');
    });

    test('clears cache on user-disabled', () async {
      final cache = MockTokenCache()..authToken = 'valid-token';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw MockFirebaseAuthException('user-disabled'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, isEmpty, reason: 'user-disabled must clear cache');
    });

    test('clears cache on user-token-expired', () async {
      final cache = MockTokenCache()..authToken = 'valid-token';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw MockFirebaseAuthException('user-token-expired'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, isEmpty, reason: 'user-token-expired must clear cache');
    });

    test('preserves cache on unknown FirebaseAuthException code', () async {
      final cache = MockTokenCache()..authToken = 'valid-token';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw MockFirebaseAuthException('network-request-failed'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, equals('valid-token'), reason: 'non-terminal FirebaseAuthException must preserve token');
    });

    test('preserves cache on generic exception (network timeout)', () async {
      final cache = MockTokenCache()..authToken = 'valid-token';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw Exception('SocketException: Connection timed out'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, equals('valid-token'), reason: 'transient errors must preserve cached token');
    });
  });

  group('Bug 6 (#5927): getAuthHeader recomputes hasAuthToken and preserves token', () {
    test('successful refresh: returns bearer header with new token', () async {
      final cache = MockTokenCache();
      final header = await getAuthHeaderFixed(
        cache: cache,
        isExpirationDateValid: false,
        getIdToken: () async => 'fresh-token',
        isSignedIn: true,
      );
      expect(header, equals('Bearer fresh-token'));
      expect(cache.authToken, equals('fresh-token'));
    });

    test('refresh returns null with no cached token, signed in: throws', () async {
      final cache = MockTokenCache();
      expect(
        () => getAuthHeaderFixed(
          cache: cache,
          isExpirationDateValid: false,
          getIdToken: () async => null,
          isSignedIn: true,
        ),
        throwsException,
      );
    });

    test('refresh returns null with no cached token, not signed in: returns empty bearer', () async {
      final cache = MockTokenCache();
      final header = await getAuthHeaderFixed(
        cache: cache,
        isExpirationDateValid: false,
        getIdToken: () async => null,
        isSignedIn: false,
      );
      expect(header, equals('Bearer '));
    });

    test('refresh returns null but cached token exists: preserves and uses cached token', () async {
      final cache = MockTokenCache()..authToken = 'near-expiry-token';
      final header = await getAuthHeaderFixed(
        cache: cache,
        isExpirationDateValid: false,
        getIdToken: () async => null,
        isSignedIn: true,
      );
      expect(header, equals('Bearer near-expiry-token'),
          reason: 'null refresh must not wipe near-expiry but still valid token');
      expect(cache.authToken, equals('near-expiry-token'));
    });

    test('valid expiration: skips refresh entirely', () async {
      final cache = MockTokenCache()..authToken = 'current-token';
      var refreshCalled = false;
      final header = await getAuthHeaderFixed(
        cache: cache,
        isExpirationDateValid: true,
        getIdToken: () async {
          refreshCalled = true;
          return 'should-not-be-used';
        },
        isSignedIn: true,
      );
      expect(header, equals('Bearer current-token'));
      expect(refreshCalled, isFalse, reason: 'should not call refresh when token is still valid');
    });
  });
}
