import 'package:flutter_test/flutter_test.dart';

/// Tests for the token refresh infinite retry loop fix (#5448).
///
/// The production code uses singletons (FirebaseAuth, SharedPreferencesUtil,
/// AuthService) that aren't injectable, so these tests exercise the exact
/// same branching logic via minimal abstractions that mirror the production flow.

/// Simulates SharedPreferencesUtil token cache behavior.
class MockTokenCache {
  String authToken = '';
  int tokenExpirationTime = 0;
}

/// Simulates AuthService.getIdToken() logic after fix.
/// Returns null (not cached expired token) when currentUser is null or refresh throws.
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
  } catch (e) {
    cache.authToken = '';
    cache.tokenExpirationTime = 0;
    return null;
  }
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

    test('fixed: returns null when refresh throws', () async {
      final cache = MockTokenCache()..authToken = 'expired-token-abc';
      final result = await getIdTokenFixed(
        hasCurrentUser: true,
        refreshToken: () async => throw Exception('network error'),
        cache: cache,
      );
      expect(result, isNull);
      expect(cache.authToken, isEmpty, reason: 'cache must be cleared on refresh failure');
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
}
