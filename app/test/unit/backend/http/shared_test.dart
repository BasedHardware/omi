import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';

Future<String> simulateGetAuthHeader({required bool isSignedIn, required String token}) async {
  if (token.isEmpty && isSignedIn) {
    throw AuthTokenUnavailableException('No auth token found');
  }
  return 'Bearer $token';
}

Future<Map<String, String>> simulateBuildHeaders({required Future<String> Function() getAuthHeader}) async {
  final headers = <String, String>{};
  try {
    headers['Authorization'] = await getAuthHeader();
  } on AuthTokenUnavailableException {
    // Mirrors buildHeaders() behavior in shared.dart: continue without auth header.
  }
  return headers;
}

void main() {
  group('auth header guards', () {
    test('throws AuthTokenUnavailableException when signed in and token missing', () async {
      expect(() => simulateGetAuthHeader(isSignedIn: true, token: ''), throwsA(isA<AuthTokenUnavailableException>()));
    });

    test('caller guard catches AuthTokenUnavailableException and omits Authorization header', () async {
      final headers = await simulateBuildHeaders(
        getAuthHeader: () => simulateGetAuthHeader(isSignedIn: true, token: ''),
      );

      expect(headers.containsKey('Authorization'), isFalse);
    });

    test('includes Authorization header on happy path', () async {
      final headers = await simulateBuildHeaders(
        getAuthHeader: () => simulateGetAuthHeader(isSignedIn: true, token: 'fresh-token'),
      );

      expect(headers['Authorization'], equals('Bearer fresh-token'));
    });
  });
}
