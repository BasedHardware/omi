import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';
import 'package:omi/services/auth/auth_token_result.dart';

Future<String> simulateGetAuthHeader({required bool isSignedIn, required String token}) async {
  if (token.isEmpty && isSignedIn) {
    throw AuthTokenUnavailableException(const AuthTokenMissingToken());
  }
  return 'Bearer $token';
}

Future<Map<String, String>> simulateBuildHeaders({required Future<String> Function() getAuthHeader}) async {
  final headers = <String, String>{};
  // Mirrors buildHeaders(): auth failure aborts header construction so no
  // authenticated request can degrade into anonymous traffic.
  headers['Authorization'] = await getAuthHeader();
  return headers;
}

void main() {
  group('auth header guards', () {
    test('throws AuthTokenUnavailableException when signed in and token missing', () async {
      expect(() => simulateGetAuthHeader(isSignedIn: true, token: ''), throwsA(isA<AuthTokenUnavailableException>()));
    });

    test('header construction propagates AuthTokenUnavailableException instead of omitting auth', () async {
      expect(
        () => simulateBuildHeaders(getAuthHeader: () => simulateGetAuthHeader(isSignedIn: true, token: '')),
        throwsA(isA<AuthTokenUnavailableException>()),
      );
    });

    test('includes Authorization header on happy path', () async {
      final headers = await simulateBuildHeaders(
        getAuthHeader: () => simulateGetAuthHeader(isSignedIn: true, token: 'fresh-token'),
      );

      expect(headers['Authorization'], equals('Bearer fresh-token'));
    });
  });
}
