import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/shared.dart';

String _tokenWithExpiration(DateTime expiration) {
  final payload =
      base64Url.encode(utf8.encode(jsonEncode({'exp': expiration.millisecondsSinceEpoch ~/ 1000}))).replaceAll('=', '');
  return 'header.$payload.signature';
}

void main() {
  test('JWT expiry overrides a stale future cached expiry', () {
    final expiredAt = DateTime.utc(2026, 8, 24);
    final staleCachedExpiry = DateTime.utc(2026, 9, 1).millisecondsSinceEpoch;

    final expiry = resolveAuthTokenExpiration(
      token: _tokenWithExpiration(expiredAt),
      cachedExpirationTime: staleCachedExpiry,
    );

    expect(expiry, expiredAt);
  });
}
